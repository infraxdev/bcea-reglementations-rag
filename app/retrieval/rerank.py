from __future__ import annotations

from ..ingestion.models import SearchHit
from .interfaces import Reranker


class NotConfiguredReranker(Reranker):
    """Default Reranker — no cross-encoder/rerank model has been chosen yet.

    TODO: implement against a cross-encoder (e.g. a local sentence-transformers
    CrossEncoder, or a hosted rerank API) and wire it into retrieval/pipeline.py in place
    of this class.
    """

    async def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        raise NotImplementedError(
            "No reranker configured. Implement app.retrieval.rerank.Reranker against a "
            "cross-encoder and use it in retrieval/pipeline.py."
        )
