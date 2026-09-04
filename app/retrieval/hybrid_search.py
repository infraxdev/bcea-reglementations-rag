from __future__ import annotations

from ..ingestion.embed import NotConfiguredEmbedder
from ..ingestion.interfaces import Embedder
from ..ingestion.models import SearchHit
from ..ingestion.vector_store import QdrantVectorStore, VectorStore

_RRF_K = 60  # standard reciprocal-rank-fusion damping constant


class HybridSearcher:
    """Hybrid search box: combines a dense-vector leg (semantic similarity) with a
    keyword leg (Qdrant full-text MatchText filter on the same vector search) and fuses
    the two ranked lists via reciprocal rank fusion. Both legs go through the same
    Embedder + VectorStore, so this becomes fully functional as soon as an Embedder is
    configured (see ingestion/embed.py)."""

    def __init__(self, embedder: Embedder | None = None, vector_store: VectorStore | None = None) -> None:
        self.embedder = embedder or NotConfiguredEmbedder()
        self.vector_store = vector_store or QdrantVectorStore()

    async def search(self, query: str, top_k: int = 20) -> list[SearchHit]:
        query_vector = await self.embedder.embed_query(query)
        vector_hits = await self.vector_store.search(query_vector, top_k=top_k)
        keyword_hits = await self.vector_store.search(query_vector, top_k=top_k, keyword=query)
        return self._reciprocal_rank_fusion([vector_hits, keyword_hits], top_k)

    @staticmethod
    def _reciprocal_rank_fusion(ranked_lists: list[list[SearchHit]], top_k: int) -> list[SearchHit]:
        fused_scores: dict[str, float] = {}
        hits_by_id: dict[str, SearchHit] = {}
        for ranked in ranked_lists:
            for rank, hit in enumerate(ranked):
                fused_scores[hit.chunk_id] = fused_scores.get(hit.chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
                hits_by_id[hit.chunk_id] = hit
        ordered_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
        return [
            hits_by_id[cid].model_copy(update={"score": fused_scores[cid]}) for cid in ordered_ids[:top_k]
        ]
