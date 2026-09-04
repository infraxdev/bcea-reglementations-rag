from __future__ import annotations

from pydantic import BaseModel, Field

from ..ingestion.models import SearchHit


class RouterDecision(BaseModel):
    in_scope: bool
    reason: str


class RewrittenQuery(BaseModel):
    query: str
    extracted_metadata: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    query: str
    in_scope: bool
    router_reason: str
    hits: list[SearchHit] = Field(default_factory=list)
    prompt: str | None = Field(None, description="Assembled prompt (context + citations), unset when out of scope.")
