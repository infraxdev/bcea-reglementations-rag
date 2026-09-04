from __future__ import annotations

from .interfaces import QueryRewriter
from .models import RewrittenQuery


class PassthroughRewriter(QueryRewriter):
    """Default QueryRewriter — returns the query unchanged with no extracted metadata.

    TODO: replace with real query rewriting (e.g. an LLM call that expands abbreviations,
    normalizes French regulatory terminology, and extracts structured filters like date
    ranges or document type) once a provider is chosen. Keeping this as a no-op default
    means hybrid_search still works today, just without metadata-filtered search.
    """

    async def rewrite(self, query: str) -> RewrittenQuery:
        return RewrittenQuery(query=query, extracted_metadata={})
