from __future__ import annotations

from abc import ABC, abstractmethod

from ..ingestion.models import SearchHit
from .models import RewrittenQuery, RouterDecision


class QueryRouter(ABC):
    """Query router. Decides whether a user query is in the BCEAO/regulatory scope this
    RAG system is meant to answer, before any retrieval or LLM call happens."""

    @abstractmethod
    async def route(self, query: str) -> RouterDecision: ...


class QueryRewriter(ABC):
    """Rewrite query. Normalizes the query and pulls out structured metadata (date
    ranges, document types, etc.) to use as search filters."""

    @abstractmethod
    async def rewrite(self, query: str) -> RewrittenQuery: ...


class Reranker(ABC):
    """Rerank. Cross-encoder (or similar) re-scoring of hybrid search's top-k candidates."""

    @abstractmethod
    async def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]: ...
