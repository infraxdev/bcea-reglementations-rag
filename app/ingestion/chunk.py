from __future__ import annotations

import hashlib
import re

from .interfaces import Chunker
from .models import DocChunk, ParsedDocument, ParsedPage

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")


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
