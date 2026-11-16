from __future__ import annotations

from pydantic import BaseModel, Field

from ..ingestion.models import SearchHit


class RouterDecision(BaseModel):
    in_scope: bool
    reason: str
    # True for greetings/thanks/farewells/introductions etc. — still out of scope (no
    # retrieval, and no further LLM call), but answered as small talk rather than with
    # the regulatory-scope refusal.
    courtesy: bool = False
    # True for general finance/economics questions that don't depend on the regulatory
    # texts — no retrieval, and no router-written reply: generation/pipeline.py answers
    # them (via `rewritten_query`) with the generation LLM and the full conversation
    # history.
    general_finance: bool = False
    # Set by routers that produce these in the same call as the scope decision (see
    # retrieval/router.py's LLMScopeRouter). `rewritten_query` lets retrieval/pipeline.py
    # skip the separate rewrite call when in scope, and is the self-contained question
    # handed to the generation LLM for general finance; `reply` (courtesy / out of scope)
    # is the text shown to the user. Either may be None, in which case the pipeline falls
    # back to the QueryRewriter / the raw query / generation/pipeline.py's fixed replies.
    rewritten_query: str | None = None
    reply: str | None = None


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class RewrittenQuery(BaseModel):
    query: str
    extracted_metadata: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    query: str
    in_scope: bool
    router_reason: str
    courtesy: bool = False
    general_finance: bool = False
    reply: str | None = Field(None, description="Router-written reply for a message that isn't in scope, if any.")
    rewritten_query: str | None = Field(
        None,
        description="Rewritten query: sent to hybrid search when in scope, or to the generation LLM for general finance.",
    )
    hits: list[SearchHit] = Field(default_factory=list)
    prompt: str | None = Field(
        None, description="Assembled user-turn message (context + citations), unset when out of scope."
    )
    # Pass-through from the caller (see generation/memory.py's fold_history): the
    # already-capped verbatim prior turns and rolling summary of anything older. Neither
    # is used by retrieval itself, but riding along on RetrievalResult saves
    # generation/pipeline.py from threading them through retrieve() as separate params.
    history: list[ChatTurn] = Field(default_factory=list)
    history_summary: str | None = None
