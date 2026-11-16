from __future__ import annotations

import asyncio

from .interfaces import Embedder
from .models import DocChunk, EmbeddedChunk, QueryEmbedding

# multilingual-e5-large: one of the strongest open multilingual (French-inclusive)
# retrieval embeddings available through fastembed (BGE-M3 isn't in fastembed's dense
# model catalog). BM25 covers the lexical leg — exact article numbers and defined terms
# that a dense embedding can blur. Both run locally via fastembed/ONNX so BCEAO's
# regulatory documents never leave the host.
#
# DENSE_MODEL has no leading underscore because chunk.SemanticChunker reuses it for
# sentence-embedding-based boundary detection — one dense model, one place that names it.
DENSE_MODEL = "intfloat/multilingual-e5-large"
_SPARSE_MODEL = "Qdrant/bm25"
_SPARSE_LANGUAGE = "french"

# E5 models are trained on inputs prefixed by role, and score noticeably worse without
# it — fastembed doesn't add this prefix for us, so we do it explicitly.
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "


class NotConfiguredEmbedder(Embedder):
    """Fallback Embedder for when fastembed (or its model weights) isn't available —
    keeps the pipeline's failure mode explicit instead of silently no-op-ing."""

    async def embed_chunks(self, chunks: list[DocChunk]) -> list[EmbeddedChunk]:
        raise NotImplementedError(
            "No embedder configured. Install fastembed (see requirements.txt) and use "
            "FastEmbedEmbedder, or implement app.ingestion.embed.Embedder against a "
            "different dense (+ optional sparse) embedding model."
        )

    async def embed_query(self, query: str) -> QueryEmbedding:
        raise NotImplementedError(
            "No embedder configured. Install fastembed (see requirements.txt) and use "
            "FastEmbedEmbedder, or implement app.ingestion.embed.Embedder against a "
            "different dense (+ optional sparse) embedding model."
        )


class FastEmbedEmbedder(Embedder):
    """Default Embedder — multilingual-e5-large dense vectors + BM25 sparse vectors, both
    computed locally via fastembed. Model loading is lazy and happens once per process;
    the (synchronous, CPU-bound) embedding calls run in a thread so they don't block the
    event loop."""

    def __init__(self) -> None:
        self._dense_model = None
        self._sparse_model = None

    def _get_dense_model(self):
        if self._dense_model is None:
            from fastembed import TextEmbedding

            self._dense_model = TextEmbedding(model_name=DENSE_MODEL)
        return self._dense_model

    def _get_sparse_model(self):
        if self._sparse_model is None:
            from fastembed.sparse.bm25 import Bm25

            self._sparse_model = Bm25(model_name=_SPARSE_MODEL, language=_SPARSE_LANGUAGE)
        return self._sparse_model

    async def embed_chunks(self, chunks: list[DocChunk]) -> list[EmbeddedChunk]:
        if not chunks:
            return []
        texts = [chunk.text for chunk in chunks]
        prefixed = [_PASSAGE_PREFIX + text for text in texts]
        dense_vectors = await asyncio.to_thread(lambda: list(self._get_dense_model().embed(prefixed)))
        sparse_vectors = await asyncio.to_thread(lambda: list(self._get_sparse_model().embed(texts)))
        return [
            EmbeddedChunk(
                chunk=chunk,
                dense_vector=dense.tolist(),
                sparse_vector=dict(zip(sparse.indices.tolist(), sparse.values.tolist())),
            )
            for chunk, dense, sparse in zip(chunks, dense_vectors, sparse_vectors)
        ]

    async def embed_query(self, query: str) -> QueryEmbedding:
        dense_vector = await asyncio.to_thread(lambda: next(iter(self._get_dense_model().query_embed(_QUERY_PREFIX + query))))
        sparse_vector = await asyncio.to_thread(lambda: next(iter(self._get_sparse_model().query_embed(query))))
        return QueryEmbedding(
            dense_vector=dense_vector.tolist(),
            sparse_vector=dict(zip(sparse_vector.indices.tolist(), sparse_vector.values.tolist())),
        )
