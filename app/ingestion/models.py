from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class ParsedPage(BaseModel):
    page_number: int
    text: str
    has_text_layer: bool = Field(
        True, description="False when the page looks scanned (little/no native text) and should go through VLM normalize."
    )


class ParsedDocument(BaseModel):
    """Output of the Parse stage, before any VLM normalization of scanned pages."""

    source_url: str
    source_location: str = Field(description="Where the original file is stored (crawler storage_location).")
    title: str | None = None
    pages: list[ParsedPage]

    @property
    def needs_normalization(self) -> bool:
        return any(not p.has_text_layer for p in self.pages)


class DocChunk(BaseModel):
    """Output of the Chunk stage: semantic unit + metadata, not yet embedded."""

    chunk_id: str
    source_url: str
    title: str | None = None
    page_number: int | None = None
    chunk_index: int
    text: str
    metadata: dict = Field(default_factory=dict)


class EmbeddedChunk(BaseModel):
    """A DocChunk plus its dense/sparse vectors, ready for upsert into the vector store."""

    chunk: DocChunk
    dense_vector: list[float]
    sparse_vector: dict[int, float] | None = None


class QueryEmbedding(BaseModel):
    """A query's dense/sparse vectors, ready for the vector store's search leg(s)."""

    dense_vector: list[float]
    sparse_vector: dict[int, float] | None = None


class SearchHit(BaseModel):
    """A single vector-store search result, en route to retrieval's rerank + prompt assembly."""

    chunk_id: str
    source_url: str
    title: str | None = None
    page_number: int | None = None
    text: str
    score: float
    metadata: dict = Field(default_factory=dict)


class IndexResult(BaseModel):
    job_id: str
    documents_processed: int = 0
    documents_skipped: int = Field(0, description="Already moved into processed/ by a prior run.")
    chunks_indexed: int = 0
    errors: list[str] = Field(default_factory=list)


class IngestProgress(BaseModel):
    """Live progress snapshot for a background ingest run — see ingestion/progress.py.
    Polled by GET /ingest/{job_id}/progress; rate/eta are computed fields so callers get
    a tqdm-style "docs/sec, ETA" readout without recomputing it themselves."""

    job_id: str
    status: str = Field(description="'queued' | 'running' | 'completed' | 'failed'")
    attempts: int = Field(0, description="How many times a worker has started this run.")
    total_documents: int
    documents_processed: int = 0
    documents_skipped: int = 0
    chunks_indexed: int = 0
    current_file: str | None = None
    errors: list[str] = Field(default_factory=list)
    started_at: float
    updated_at: float

    @computed_field  # type: ignore[misc]
    @property
    def documents_done(self) -> int:
        return self.documents_processed + self.documents_skipped

    @computed_field  # type: ignore[misc]
    @property
    def rate_docs_per_sec(self) -> float:
        elapsed = self.updated_at - self.started_at
        return round(self.documents_done / elapsed, 3) if elapsed > 0 else 0.0

    @computed_field  # type: ignore[misc]
    @property
    def eta_seconds(self) -> float | None:
        remaining = self.total_documents - self.documents_done
        rate = self.rate_docs_per_sec
        return round(remaining / rate, 1) if rate > 0 and remaining > 0 else None
