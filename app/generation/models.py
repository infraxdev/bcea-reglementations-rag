from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..ingestion.models import SearchHit
from ..retrieval.models import ChatTurn


class PolicyGateResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    query: str
    in_scope: bool
    # How the message was handled: "in_scope" answers are grounded in retrieved
    # documents; "general_finance" answers come from the LLM's own knowledge (no
    # retrieval, no sources); "courtesy" and "out_of_scope" are the router's short reply.
    route: Literal["in_scope", "general_finance", "courtesy", "out_of_scope"]
    answer: str
    sources: list[SearchHit] = Field(default_factory=list)
    policy: PolicyGateResult | None = None
    # Authoritative next-turn conversation state (see generation/memory.py's
    # fold_history): the caller should resend these verbatim as `history` /
    # `history_summary` on its next /query request instead of replaying the full
    # on-screen transcript. Already includes this turn's query + answer.
    history: list[ChatTurn] = Field(default_factory=list)
    history_summary: str | None = None
