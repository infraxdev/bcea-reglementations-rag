from __future__ import annotations

import asyncio
from pathlib import Path

from .interfaces import Parser
from .models import ParsedDocument, ParsedPage

# Below this many characters of native text, a page is treated as "scanned" (no
# usable text layer) and routed to VLM normalize rather than trusted as-is.
_MIN_CHARS_FOR_TEXT_LAYER = 20


class DoclingParser(Parser):
    """Default Parser implementation, using IBM's Docling (https://github.com/DS4SD/docling)
    to convert PDFs/Office docs/HTML into page-level text. Runs the (synchronous, CPU-bound)
    Docling conversion in a thread so it doesn't block the event loop."""

    def __init__(self) -> None:
        self._converter = None  # built lazily — Docling's import/model load is heavy

    def _get_converter(self):
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    async def parse(self, path: Path, source_url: str, source_location: str) -> ParsedDocument:
        return await asyncio.to_thread(self._parse_sync, path, source_url, source_location)

    def _parse_sync(self, path: Path, source_url: str, source_location: str) -> ParsedDocument:
        converter = self._get_converter()
        result = converter.convert(str(path))
        doc = result.document

        pages: list[ParsedPage] = []
        page_texts = self._per_page_text(doc)
        for page_number, text in page_texts:
            pages.append(
                ParsedPage(
                    page_number=page_number,
                    text=text,
                    has_text_layer=len(text.strip()) >= _MIN_CHARS_FOR_TEXT_LAYER,
                )
            )
        if not pages:
            # Docling exposed no per-page breakdown (e.g. a single-page HTML doc) —
            # fall back to the whole-document markdown as one page.
            full_text = doc.export_to_markdown()
            pages.append(
                ParsedPage(page_number=1, text=full_text, has_text_layer=len(full_text.strip()) >= _MIN_CHARS_FOR_TEXT_LAYER)
            )

        title = getattr(doc, "name", None) or path.stem
        return ParsedDocument(source_url=source_url, source_location=source_location, title=title, pages=pages)

    @staticmethod
    def _per_page_text(doc) -> list[tuple[int, str]]:
        """Best-effort per-page text extraction. Docling's API for this has shifted across
        versions, so this degrades gracefully rather than hard-failing on a given version."""
        try:
            page_numbers = sorted(doc.pages.keys())
        except Exception:
            return []
        out: list[tuple[int, str]] = []
        for page_no in page_numbers:
            try:
                text = doc.export_to_markdown(page_no=page_no)
            except TypeError:
                # Older/newer Docling versions may not support the page_no kwarg —
                # give up on per-page granularity rather than guessing at an API shape.
                return []
            out.append((page_no, text))
        return out
