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

    # If more than this fraction of pages come back without a native text layer,
    # the document is treated as scanned and re-parsed with OCR.
    _OCR_FALLBACK_THRESHOLD = 0.5

    def __init__(self) -> None:
        self._converter = None  # built lazily — Docling's import/model load is heavy
        self._ocr_converter = None

    def _get_converter(self):
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    def _get_ocr_converter(self):
        if self._ocr_converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import OcrMode, PdfPipelineOptions, RapidOcrOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            # BCEAO regulatory PDFs are frequently scanned French-language documents with
            # no native text layer — full-page RapidOCR turns those into usable text.
            ocr_options = RapidOcrOptions(lang=["fr"], backend="onnxruntime", mode=OcrMode.FULL_PAGE)
            pipeline_options = PdfPipelineOptions(do_ocr=True, do_table_structure=True, ocr_options=ocr_options)
            self._ocr_converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
        return self._ocr_converter

    async def parse(self, path: Path, source_url: str, source_location: str) -> ParsedDocument:
        return await asyncio.to_thread(self._parse_sync, path, source_url, source_location)

    def _parse_sync(self, path: Path, source_url: str, source_location: str) -> ParsedDocument:
        doc, pages = self._convert(path, self._get_converter())
        if self._needs_ocr(pages):
            doc, pages = self._convert(path, self._get_ocr_converter())

        title = getattr(doc, "name", None) or path.stem
        return ParsedDocument(source_url=source_url, source_location=source_location, title=title, pages=pages)

    @classmethod
    def _needs_ocr(cls, pages: list[ParsedPage]) -> bool:
        if not pages:
            return True
        missing = sum(1 for p in pages if not p.has_text_layer)
        return missing / len(pages) > cls._OCR_FALLBACK_THRESHOLD

    @staticmethod
    def _convert(path: Path, converter) -> tuple[object, list[ParsedPage]]:
        result = converter.convert(str(path))
        doc = result.document

        pages: list[ParsedPage] = []
        page_texts = DoclingParser._per_page_text(doc)
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
        return doc, pages

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
