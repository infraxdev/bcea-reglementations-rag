from __future__ import annotations

from pydantic import BaseModel, Field


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
    chunks_indexed: int = 0
    errors: list[str] = Field(default_factory=list)
