from __future__ import annotations

from pydantic import BaseModel, Field

from ..ingestion.models import SearchHit


class PolicyGateResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    query: str
    in_scope: bool
    answer: str
    sources: list[SearchHit] = Field(default_factory=list)
    policy: PolicyGateResult | None = None
