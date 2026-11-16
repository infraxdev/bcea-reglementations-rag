from __future__ import annotations

from ..ingestion.embed import FastEmbedEmbedder
from ..ingestion.interfaces import Embedder
from ..ingestion.models import SearchHit
from ..ingestion.vector_store import QdrantVectorStore, VectorStore


class HybridSearcher:
    """Hybrid search box: embeds the query into dense (semantic) + sparse (BM25, lexical)
    vectors and lets Qdrant fuse both legs server-side via reciprocal rank fusion
    (see VectorStore.search)."""

    def __init__(self, embedder: Embedder | None = None, vector_store: VectorStore | None = None) -> None:
        self.embedder = embedder or FastEmbedEmbedder()
        self.vector_store = vector_store or QdrantVectorStore()

    async def search(self, query: str, top_k: int = 20) -> list[SearchHit]:
        query_embedding = await self.embedder.embed_query(query)
        return await self.vector_store.search(
            query_embedding.dense_vector, query_embedding.sparse_vector, top_k=top_k
        )
