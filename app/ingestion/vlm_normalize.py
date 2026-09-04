from __future__ import annotations

from pathlib import Path

from .interfaces import Normalizer
from .models import ParsedPage


class NotConfiguredNormalizer(Normalizer):
    """Default Normalizer — no vision-capable model has been chosen yet.

    TODO: implement against a VLM (e.g. Claude with image input, GPT-4V) that takes the
    rendered page image + Docling's best-effort text/table extraction and returns cleaned
    markdown. Wire the concrete implementation in ingestion/pipeline.py in place of this class.
    """

    async def normalize(self, path: Path, page: ParsedPage) -> ParsedPage:
        raise NotImplementedError(
            "No VLM normalizer configured. Implement app.ingestion.vlm_normalize.Normalizer "
            "against a vision-capable model and use it in ingestion/pipeline.py."
        )
