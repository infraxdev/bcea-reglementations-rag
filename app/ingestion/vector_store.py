from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from ..config import get_qdrant_settings
from .models import EmbeddedChunk, SearchHit

# Point IDs are deterministic UUIDv5s derived from chunk_id, since Qdrant only accepts
# unsigned ints or UUID strings as point IDs (not arbitrary hex) — this also makes
# re-indexing the same chunk idempotent (same chunk_id -> same point, upsert overwrites).
_POINT_ID_NAMESPACE = uuid.UUID("6f1f7f2e-3b8b-4e3a-9d7e-3a6b6b9c8f10")


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk_id))


class VectorStore(ABC):
    """Qdrant box in the diagram: stores embedded chunks and serves hybrid search."""

    @abstractmethod
    async def ensure_collection(self, vector_size: int) -> None: ...

    @abstractmethod
    async def upsert(self, chunks: list[EmbeddedChunk]) -> None: ...

    @abstractmethod
    async def search(
        self, dense_vector: list[float], sparse_vector: dict[int, float] | None = None, top_k: int = 20
    ) -> list[SearchHit]: ...


class QdrantVectorStore(VectorStore):
    """Default VectorStore implementation, backed by Qdrant. Dense (semantic) and sparse
    (BM25, lexical) vectors are stored as separate named vectors on the same point; when a
    search provides both, Qdrant fuses the two legs server-side via reciprocal rank fusion
    (Query API prefetch + FusionQuery), so no separate BM25/Elasticsearch dependency is
    needed alongside the vector store."""

    def __init__(self) -> None:
        settings = get_qdrant_settings()
        self._collection = settings.collection
        self._client = None
        self._settings = settings

    def _get_client(self):
        if self._client is None:
            from qdrant_client import AsyncQdrantClient

            self._client = AsyncQdrantClient(url=self._settings.url, api_key=self._settings.api_key)
        return self._client

    async def ensure_collection(self, vector_size: int) -> None:
        from qdrant_client import models as qmodels

        client = self._get_client()
        if not await client.collection_exists(self._collection):
            await client.create_collection(
                collection_name=self._collection,
                vectors_config={"dense": qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE)},
                # Modifier.IDF lets Qdrant compute true corpus-wide IDF over the BM25 term
                # weights at query time, rather than trusting fastembed's per-document estimate.
                sparse_vectors_config={"sparse": qmodels.SparseVectorParams(modifier=qmodels.Modifier.IDF)},
            )
            await client.create_payload_index(
                collection_name=self._collection,
                field_name="text",
                field_schema=qmodels.TextIndexParams(
                    type=qmodels.TextIndexType.TEXT,
                    tokenizer=qmodels.TokenizerType.WORD,
                    lowercase=True,
                ),
            )

    async def upsert(self, chunks: list[EmbeddedChunk]) -> None:
        from qdrant_client import models as qmodels

        client = self._get_client()
        points = []
        for ec in chunks:
            vector: dict[str, object] = {"dense": ec.dense_vector}
            if ec.sparse_vector:
                vector["sparse"] = qmodels.SparseVector(
                    indices=list(ec.sparse_vector.keys()), values=list(ec.sparse_vector.values())
                )
            points.append(
                qmodels.PointStruct(
                    id=_point_id(ec.chunk.chunk_id),
                    vector=vector,
                    payload={
                        "chunk_id": ec.chunk.chunk_id,
                        "source_url": ec.chunk.source_url,
                        "title": ec.chunk.title,
                        "page_number": ec.chunk.page_number,
                        "text": ec.chunk.text,
                        "metadata": ec.chunk.metadata,
                    },
                )
            )
        await client.upsert(collection_name=self._collection, points=points)

    async def search(
        self, dense_vector: list[float], sparse_vector: dict[int, float] | None = None, top_k: int = 20
    ) -> list[SearchHit]:
        from qdrant_client import models as qmodels

        client = self._get_client()
        if sparse_vector:
            prefetch = [
                qmodels.Prefetch(query=dense_vector, using="dense", limit=top_k),
                qmodels.Prefetch(
                    query=qmodels.SparseVector(
                        indices=list(sparse_vector.keys()), values=list(sparse_vector.values())
                    ),
                    using="sparse",
                    limit=top_k,
                ),
            ]
            results = await client.query_points(
                collection_name=self._collection,
                prefetch=prefetch,
                query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )
        else:
            results = await client.query_points(
                collection_name=self._collection,
                query=dense_vector,
                using="dense",
                limit=top_k,
                with_payload=True,
            )
        hits: list[SearchHit] = []
        for point in results.points:
            payload = point.payload or {}
            hits.append(
                SearchHit(
                    chunk_id=payload.get("chunk_id", str(point.id)),
                    source_url=payload.get("source_url", ""),
                    title=payload.get("title"),
                    page_number=payload.get("page_number"),
                    text=payload.get("text", ""),
                    score=point.score,
                    metadata=payload.get("metadata", {}),
                )
            )
        return hits
