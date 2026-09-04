from __future__ import annotations

import re

from .interfaces import QueryRouter
from .models import RouterDecision

# Default scope keywords for the BCEAO regulatory domain (French — the crawled site is
# French-language). Extend/replace via the `scope_keywords` constructor arg, or swap this
# whole class out for an LLM-based classifier later via the QueryRouter interface.
DEFAULT_SCOPE_KEYWORDS: tuple[str, ...] = (
    "bceao",
    "uemoa",
    "banque centrale",
    "reglementation",
    "règlementation",
    "reglement",
    "règlement",
    "circulaire",
    "instruction",
    "directive",
    "banque",
    "bancaire",
    "etablissement de credit",
    "établissement de crédit",
    "union monetaire",
    "union monétaire",
    "change",
    "devise",
    "monnaie",
    "franc cfa",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


class KeywordScopeRouter(QueryRouter):
    """Default QueryRouter — a cheap keyword-presence heuristic that runs before any LLM
    call, matching the diagram's "no LLM call" out-of-scope path. Good enough as a first
    gate; swap for an LLM/embedding classifier later if the false-negative rate matters."""

    def __init__(self, scope_keywords: tuple[str, ...] = DEFAULT_SCOPE_KEYWORDS) -> None:
        self._keywords = tuple(_normalize(k) for k in scope_keywords)

    async def route(self, query: str) -> RouterDecision:
        normalized = _normalize(query)
        if not normalized:
            return RouterDecision(in_scope=False, reason="empty query")
        matched = [k for k in self._keywords if k in normalized]
        if matched:
            return RouterDecision(in_scope=True, reason=f"matched scope keyword(s): {', '.join(matched)}")
        return RouterDecision(in_scope=False, reason="no BCEAO/regulatory scope keyword matched")
