from __future__ import annotations

from .interfaces import Embedder
from .models import DocChunk, EmbeddedChunk


class NotConfiguredEmbedder(Embedder):
    """Default Embedder — no dense/sparse embedding model has been chosen yet.

    TODO: implement against your chosen provider(s), e.g.:
      - dense: an API-based embedding model, or a local sentence-transformers model
      - sparse: SPLADE, or a BM25-style term-weight vector
    Wire the concrete implementation in ingestion/pipeline.py and retrieval/hybrid_search.py
    in place of this class.
    """

    async def embed_chunks(self, chunks: list[DocChunk]) -> list[EmbeddedChunk]:
        raise NotImplementedError(
            "No embedder configured. Implement app.ingestion.embed.Embedder against a "
            "dense (+ optional sparse) embedding model and use it in ingestion/pipeline.py."
        )

    async def embed_query(self, query: str) -> list[float]:
        raise NotImplementedError(
            "No embedder configured. Implement app.ingestion.embed.Embedder against a "
            "dense (+ optional sparse) embedding model and use it in retrieval/hybrid_search.py."
        )
