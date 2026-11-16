from __future__ import annotations

from ..config import get_rewrite_settings
from ..generation.interfaces import Generator
from ..generation.llm import build_generator
from .interfaces import QueryRewriter
from .models import ChatTurn, RewrittenQuery

# Shared with retrieval/router.py's LLMScopeRouter, which normally produces the rewritten
# query in the same LLM call as the scope decision.
REWRITE_RULES = """  - Resolve all pronouns (it, this, they, ...) and implicit references using the conversation history, so the query is fully self-contained without the history.
  - Remove conversational filler, pleasantries, and irrelevant context.
  - Correct every misspelled word, typo and missing accent (e.g. "reserves obligatoirs" -> "réserves obligatoires"), without changing the meaning.
  - Introduce domain-specific keywords and synonyms that match regulatory documentation terminology (e.g. "banque centrale", "établissement de crédit", "réglementation", "instruction", "circulaire") where they clarify the user's intent.
  - Keep it to a single, concise standalone sentence or search phrase, in French."""

_SYSTEM_PROMPT = f"""You are a query rewriting assistant for a retrieval system that searches BCEAO/UEMOA banking regulation documents (French-language regulatory text: instructions, circulaires, règlements, directives, lois).

Given the conversation history and the user's latest message, rewrite it into a single, optimal, search-friendly query for a hybrid (dense + BM25) retrieval system. Follow these rules exactly:
{REWRITE_RULES}
  - Do not answer the question. Do not add explanation, preamble, quotation marks, or labels — output ONLY the rewritten query."""


# Per-turn cap in the transcript below: prior answers can run to thousands of characters,
# and only their gist is needed to resolve a reference in the latest message.
_MAX_TURN_CHARS = 600


def format_with_history(query: str, history: list[ChatTurn] | None) -> str:
    """Renders prior turns as a quoted transcript followed by the latest message, for use
    as a single user message. Router/rewriter prompts must not replay history as real
    chat turns: the model then treats its earlier plain-text answers as the format to
    continue in, and answers the user instead of classifying/rewriting."""
    latest = f"Latest user message: {query}"
    if not history:
        return latest
    lines = []
    for turn in history:
        content = turn.content if len(turn.content) <= _MAX_TURN_CHARS else turn.content[:_MAX_TURN_CHARS] + "…"
        lines.append(f"{turn.role}: {content}")
    transcript = "\n".join(lines)
    return f"Earlier conversation (reference only, do not reply to it):\n<<<\n{transcript}\n>>>\n\n{latest}"


class PassthroughRewriter(QueryRewriter):
    """Fallback QueryRewriter — returns the query unchanged with no extracted metadata.
    Useful for tests, or when no rewrite LLM is configured/reachable."""

    async def rewrite(self, query: str, history: list[ChatTurn] | None = None) -> RewrittenQuery:
        return RewrittenQuery(query=query, extracted_metadata={})


class LLMQueryRewriter(QueryRewriter):
    """Standalone QueryRewriter — only called when the router didn't already supply a
    rewritten query (a custom router, or LLMScopeRouter's failure path; see
    retrieval/pipeline.py). Uses a small/fast LLM (Qwen 2.5:7b via Ollama by default;
    see REWRITE_PROVIDER/REWRITE_MODEL in .env.example) to resolve pronouns and implicit
    references against conversation history, strip filler, and inject regulatory
    terminology, producing a single standalone search query. Deliberately decoupled from
    GENERATION_PROVIDER (the final-answer model) — rewriting benefits more from low
    latency than from the strongest available model."""

    def __init__(self, generator: Generator | None = None) -> None:
        if generator is None:
            settings = get_rewrite_settings()
            generator = build_generator(settings.provider, settings.model)
        self._generator = generator

    async def rewrite(self, query: str, history: list[ChatTurn] | None = None) -> RewrittenQuery:
        messages = [ChatTurn(role="user", content=format_with_history(query, history))]
        raw = await self._generator.generate(_SYSTEM_PROMPT, messages)
        rewritten = raw.strip().strip('"').strip()
        return RewrittenQuery(query=rewritten or query, extracted_metadata={})
