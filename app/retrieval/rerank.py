from __future__ import annotations

import asyncio

from ..ingestion.models import SearchHit
from .interfaces import Reranker

# jina-reranker-v2-base-multilingual: multilingual (French-inclusive) cross-encoder,
# available through fastembed's ONNX rerank models (bge-reranker-v2-m3 isn't in
# fastembed's catalog — see fastembed.rerank.cross_encoder.TextCrossEncoder.list_supported_models()).
# Runs locally, same as the dense/sparse embedder in ingestion/embed.py, so BCEAO's
# regulatory documents never leave the host for reranking either.
_MODEL = "jinaai/jina-reranker-v2-base-multilingual"


class NotConfiguredReranker(Reranker):
    """Fallback Reranker — no cross-encoder model configured. Useful for tests, or to
    skip reranking entirely (hybrid search's fused ranking is used as-is)."""

    async def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        raise NotImplementedError(
            "No reranker configured. Implement app.retrieval.rerank.Reranker against a "
            "cross-encoder and use it in retrieval/pipeline.py."
        )


class CrossEncoderReranker(Reranker):
    """Default Reranker — a cross-encoder (see retrieval/interfaces.py for the
    bi-encoder-vs-cross-encoder distinction) re-scores hybrid search's top-k candidates by
    feeding each (query, passage) pair through the model jointly, catching relevance cues
    a bi-encoder's precomputed vectors blur (exact phrasing, negation, word order). Model
    loading is lazy and happens once per process; the (synchronous, CPU-bound) scoring
    call runs in a thread so it doesn't block the event loop — same pattern as
    ingestion/embed.py's FastEmbedEmbedder."""

    def __init__(self, model_name: str = _MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self.model_name)
        return self._model

    async def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        if not hits:
            return []
        texts = [hit.text for hit in hits]
        scores = await asyncio.to_thread(lambda: list(self._get_model().rerank(query, texts)))
        ranked = sorted(zip(hits, scores), key=lambda pair: pair[1], reverse=True)
        return [hit.model_copy(update={"score": float(score)}) for hit, score in ranked[:top_k]]
