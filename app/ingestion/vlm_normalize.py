from __future__ import annotations

from pathlib import Path

from .interfaces import Normalizer
from .models import ParsedPage


class PassthroughNormalizer(Normalizer):
    """Default Normalizer — no VLM wired in yet. Leaves pages that lack a native text
    layer as-is (whatever thin/garbled text Docling + the RapidOCR fallback already
    extracted) rather than blocking the whole document from being indexed.

    TODO: implement against a VLM (e.g. DeepSeek-OCR via Ollama) that takes the rendered
    page image + Docling's best-effort text/table extraction and returns cleaned markdown,
    then wire it in ingestion/pipeline.py in place of this class to compare index quality
    against this passthrough baseline.
    """

    async def normalize(self, path: Path, page: ParsedPage) -> ParsedPage:
        return page
