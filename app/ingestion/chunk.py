from __future__ import annotations

import hashlib
import re

from .interfaces import Chunker
from .models import DocChunk, ParsedDocument, ParsedPage

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")

# Docling markdown headers, plus the structural terms regulatory text uses for
# article/chapter/section titles (French and English — BCEAO's corpus is mostly French,
# but not exclusively) even when Docling doesn't tag them as a markdown header. Anchored
# at the start and length-capped so a body sentence that merely *references* "l'article 5"
# / "article 5" mid-clause doesn't get misflagged as a heading.
_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+")
_STRUCTURAL_HEADING_RE = re.compile(
    r"^(article|chapitre|chapter|titre|title|section|livre|book|annexe|annex|partie|part)\b",
    re.IGNORECASE,
)
_MAX_HEADING_CHARS = 100

# pysbd's rule sets differ enough between languages (abbreviations, punctuation) that
# picking the wrong one measurably hurts sentence-boundary accuracy. We only ever choose
# between these two — anything else langdetect reports falls back to French, since
# that's this project's primary corpus.
_SUPPORTED_SEGMENTER_LANGUAGES = {"fr", "en"}
_DEFAULT_SEGMENTER_LANGUAGE = "fr"


def _is_heading(sentence: str) -> bool:
    stripped = sentence.strip()
    if _MARKDOWN_HEADING_RE.match(stripped):
        return True
    body = _MARKDOWN_HEADING_RE.sub("", stripped, count=1).strip()
    return len(body) <= _MAX_HEADING_CHARS and bool(_STRUCTURAL_HEADING_RE.match(body))


class SimpleChunker(Chunker):
    """Paragraph-aware chunker: packs whole paragraphs into ~chunk_size-character
    chunks (never splitting a paragraph unless it alone exceeds chunk_size), with
    a trailing overlap carried into the next chunk so context isn't lost at a
    chunk boundary. Each chunk keeps source/page metadata for citation later."""

    def __init__(self, chunk_size: int = 1200, overlap: int = 150) -> None:
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, document: ParsedDocument) -> list[DocChunk]:
        chunks: list[DocChunk] = []
        index = 0
        for page in document.pages:
            for text in self._chunk_page_text(page.text):
                chunk_id = hashlib.sha256(f"{document.source_url}:{page.page_number}:{index}".encode()).hexdigest()[:16]
                chunks.append(
                    DocChunk(
                        chunk_id=chunk_id,
                        source_url=document.source_url,
                        title=document.title,
                        page_number=page.page_number,
                        chunk_index=index,
                        text=text,
                        metadata={"source_location": document.source_location},
                    )
                )
                index += 1
        return chunks

    def _chunk_page_text(self, text: str) -> list[str]:
        paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
        if not paragraphs:
            return []

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self.chunk_size:
                if current:
                    chunks.append(current)
                    current = ""
                # A single paragraph longer than chunk_size (e.g. a dense legal clause)
                # gets hard-split rather than left as one oversized chunk.
                chunks.extend(self._hard_split(paragraph))
                continue

            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if len(candidate) <= self.chunk_size:
                current = candidate
                continue

            chunks.append(current)
            current = f"{current[-self.overlap:]}\n\n{paragraph}" if self.overlap else paragraph

        if current:
            chunks.append(current)
        return chunks

    def _hard_split(self, text: str) -> list[str]:
        step = self.chunk_size - self.overlap
        return [text[i : i + self.chunk_size] for i in range(0, len(text), step)]


class SemanticChunker(Chunker):
    """Embedding-based semantic chunker: splits each page into sentences, embeds them
    with the same dense model used for retrieval (see embed.DENSE_MODEL), and cuts a new
    chunk wherever the cosine distance between consecutive sentences spikes above an
    adaptive (percentile) threshold — i.e. wherever the topic shifts, rather than every
    chunk_size characters. Falls back to hard splitting/merging to keep chunks within
    [min_chars, max_chars].

    Slower than SimpleChunker (embeds every sentence at chunk time, not just once per
    chunk), and unlike it, doesn't carry a trailing overlap into the next chunk — cutting
    at an actual topic boundary is meant to make that unnecessary. Swap it in for
    SimpleChunker to A/B retrieval accuracy between fixed-length and semantic chunking."""

    def __init__(
        self,
        breakpoint_percentile: float = 95.0,
        min_chars: int = 200,
        max_chars: int = 2000,
        buffer_size: int = 1,
    ) -> None:
        self.breakpoint_percentile = breakpoint_percentile
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.buffer_size = buffer_size  # sentences of context merged in on each side before embedding
        self._segmenters: dict[str, object] = {}
        self._embed_model = None

    def _detect_language(self, document: ParsedDocument) -> str:
        sample = " ".join(page.text for page in document.pages)[:2000].strip()
        if not sample:
            return _DEFAULT_SEGMENTER_LANGUAGE
        from langdetect import DetectorFactory, LangDetectException, detect

        DetectorFactory.seed = 0  # langdetect is probabilistic by default; pin it for reproducible chunking
        try:
            detected = detect(sample)
        except LangDetectException:
            return _DEFAULT_SEGMENTER_LANGUAGE
        return detected if detected in _SUPPORTED_SEGMENTER_LANGUAGES else _DEFAULT_SEGMENTER_LANGUAGE

    def _get_segmenter(self, language: str):
        if language not in self._segmenters:
            import pysbd

            self._segmenters[language] = pysbd.Segmenter(language=language, clean=False)
        return self._segmenters[language]

    def _get_embed_model(self):
        if self._embed_model is None:
            from fastembed import TextEmbedding

            from .embed import DENSE_MODEL

            self._embed_model = TextEmbedding(model_name=DENSE_MODEL)
        return self._embed_model

    def chunk(self, document: ParsedDocument) -> list[DocChunk]:
        language = self._detect_language(document)
        chunks: list[DocChunk] = []
        index = 0
        for page in document.pages:
            for text in self._chunk_page_text(page.text, language):
                chunk_id = hashlib.sha256(f"{document.source_url}:{page.page_number}:{index}".encode()).hexdigest()[:16]
                chunks.append(
                    DocChunk(
                        chunk_id=chunk_id,
                        source_url=document.source_url,
                        title=document.title,
                        page_number=page.page_number,
                        chunk_index=index,
                        text=text,
                        metadata={"source_location": document.source_location},
                    )
                )
                index += 1
        return chunks

    def _chunk_page_text(self, text: str, language: str) -> list[str]:
        sentences = [s.strip() for s in self._get_segmenter(language).segment(text) if s.strip()]
        if len(sentences) < 2:
            return sentences

        import numpy as np

        # Embed each sentence merged with its neighbors (a "buffer window") rather than in
        # isolation — a single short sentence's embedding is noisy; a few words of context
        # either side places it more meaningfully in embedding space.
        windows = [
            " ".join(sentences[max(0, i - self.buffer_size) : i + self.buffer_size + 1])
            for i in range(len(sentences))
        ]
        vectors = np.array(list(self._get_embed_model().embed(windows)))
        normalized = vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)
        similarities = np.sum(normalized[:-1] * normalized[1:], axis=1)
        distances = 1.0 - similarities

        # Percentile threshold (Kamradt/LangChain-style semantic chunking): treat only the
        # sharpest jumps in distance, relative to this page's own distribution, as real
        # topic breaks — an absolute cutoff wouldn't generalize across pages of different
        # density (dense legal text vs. sparse tables).
        threshold = np.percentile(distances, self.breakpoint_percentile)
        breakpoints = {i for i, d in enumerate(distances) if d > threshold}

        # Structural override: a heading is semantically closer to the body that follows
        # it than to what precedes it, so the raw distance spike often lands right after
        # the heading instead of before it — which would end one chunk on a bare title and
        # start the next on its body. Force the cut before every heading instead (unless
        # the sentence right before it is itself a heading — e.g. "## TITRE III" directly
        # followed by "## Article 11", which should stay together as one title block), and
        # never allow a cut right after a heading (i.e. a chunk may never end on one).
        heading_flags = [_is_heading(s) for s in sentences]
        breakpoints = {i for i in breakpoints if not heading_flags[i]}
        breakpoints |= {
            i - 1 for i in range(1, len(sentences)) if heading_flags[i] and not heading_flags[i - 1]
        }
        breakpoints.discard(-1)

        groups: list[str] = []
        current = [sentences[0]]
        for i in range(1, len(sentences)):
            if (i - 1) in breakpoints:
                groups.append(" ".join(current))
                current = [sentences[i]]
            else:
                current.append(sentences[i])
        groups.append(" ".join(current))

        return self._enforce_size_bounds(groups)

    def _enforce_size_bounds(self, groups: list[str]) -> list[str]:
        merged: list[str] = []
        for group in groups:
            if merged and len(merged[-1]) < self.min_chars:
                merged[-1] = f"{merged[-1]} {group}"
            else:
                merged.append(group)
        if len(merged) > 1 and len(merged[-1]) < self.min_chars:
            merged[-2] = f"{merged[-2]} {merged[-1]}"
            merged.pop()

        bounded: list[str] = []
        for group in merged:
            if len(group) <= self.max_chars:
                bounded.append(group)
            else:
                # Topic didn't shift, the section is just long (e.g. an enumerated list) —
                # hard-split rather than leave one oversized chunk.
                bounded.extend(group[i : i + self.max_chars] for i in range(0, len(group), self.max_chars))
        return bounded
