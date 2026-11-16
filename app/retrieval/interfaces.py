from __future__ import annotations

from abc import ABC, abstractmethod

from ..ingestion.models import SearchHit
from .models import ChatTurn, RewrittenQuery, RouterDecision


class QueryRouter(ABC):
    """Query router. Decides whether the latest user message is in the BCEAO/regulatory
    scope this RAG system is meant to answer, before any retrieval happens. Takes the raw
    conversation history so a follow-up like "and its penalty?" can be understood, but
    scope is a property of the latest message, not of the conversation. May also return
    the rewritten search query or the user-facing reply on the RouterDecision."""

    @abstractmethod
    async def route(self, query: str, history: list[ChatTurn] | None = None) -> RouterDecision: ...


class QueryRewriter(ABC):
    """Rewrite query. Resolves pronouns/implicit references against conversation
    history, normalizes the query, and pulls out structured metadata (date ranges,
    document types, etc.) to use as search filters."""

    @abstractmethod
    async def rewrite(self, query: str, history: list[ChatTurn] | None = None) -> RewrittenQuery: ...


class Reranker(ABC):
    """Rerank. Cross-encoder (or similar) re-scoring of hybrid search's top-k candidates."""

    @abstractmethod
    async def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]: ...
