from __future__ import annotations

import re

from ..retrieval.models import ChatTurn, RetrievalResult
from ..retrieval.prompt_assembly import assemble_general_system, assemble_system
from .interfaces import Generator, PolicyGate
from .llm import build_generator
from .models import GenerationResult
from .policy_gate import BasicPolicyGate

# Fallbacks for when the router supplied no usable reply of its own (see
# retrieval/router.py's LLMScopeRouter, which normally writes one per message).
_OUT_OF_SCOPE_ANSWER = (
    "Cette question sort du champ de la réglementation bancaire BCEAO/UEMOA, sur lequel "
    "cet assistant est spécialisé, je ne peux donc pas y répondre."
)
_COURTESY_ANSWER = (
    "Bonjour ! Je suis un assistant spécialisé dans la réglementation bancaire "
    "BCEAO/UEMOA. Comment puis-je vous aider sur ces sujets aujourd'hui ?"
)
_POLICY_BLOCKED_ANSWER = "La réponse générée n'a pas passé le contrôle de conformité et n'est donc pas affichée."

# Second-layer defense: the system prompt (retrieval/prompt_assembly.py) already bans
# phrases like "according to the provided context", but the default local model
# (qwen2.5:7b via Ollama) doesn't reliably follow that instruction. Rather than
# withholding an otherwise-good, correctly-cited answer over a phrasing slip, strip
# these lead-in clauses deterministically wherever they appear.
_META_REFERENCE_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))"
    r"(?:according to|based on|as (?:stated|indicated|shown) (?:in|by)|per|as per)\s+"
    r"the\s+(?:provided\s+)?(?:context|documents?|excerpts?)(?:\s+(?:provided|available))?,?\s*",
    re.IGNORECASE,
)
_SENTENCE_START_RE = re.compile(r"(^|[.!?]\s+)([a-z])")


def _strip_meta_references(answer: str) -> str:
    cleaned = _META_REFERENCE_RE.sub("", answer)
    return _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), cleaned)


async def generate_answer(
    retrieval_result: RetrievalResult,
    generator: Generator | None = None,
    policy_gate: PolicyGate | None = None,
) -> GenerationResult:
    """Generation, end to end: small talk and out-of-scope messages get the router's own
    reply (or a fixed fallback) with no further LLM call; general finance questions go
    to the LLM as the router's rewritten question plus the full conversation history,
    but with no retrieved context, citations or policy gate; in-scope queries go LLM -> policy gate -> response. Either way, the
    returned GenerationResult carries the next-turn history/history_summary the caller
    should resend (see generation/memory.py)."""
    if retrieval_result.general_finance:
        generator = generator or build_generator()
        system = assemble_general_system(retrieval_result.history_summary)
        # The router's self-contained rewrite of the question (raw query if it gave none)
        # is what the LLM answers; the history kept for the next turn still records what
        # the user actually typed.
        question = retrieval_result.rewritten_query or retrieval_result.query
        messages = [*retrieval_result.history, ChatTurn(role="user", content=question)]
        answer = (await generator.generate(system, messages)).strip()
        return GenerationResult(
            query=retrieval_result.query,
            in_scope=False,
            route="general_finance",
            answer=answer,
            history=_append_exchange(retrieval_result.history, retrieval_result.query, answer),
            history_summary=retrieval_result.history_summary,
        )

    if not retrieval_result.in_scope:
        answer = retrieval_result.reply or (
            _COURTESY_ANSWER if retrieval_result.courtesy else _OUT_OF_SCOPE_ANSWER
        )
        return GenerationResult(
            query=retrieval_result.query,
            in_scope=False,
            route="courtesy" if retrieval_result.courtesy else "out_of_scope",
            answer=answer,
            history=_append_exchange(retrieval_result.history, retrieval_result.query, answer),
            history_summary=retrieval_result.history_summary,
        )

    generator = generator or build_generator()
    policy_gate = policy_gate or BasicPolicyGate()

    system = assemble_system(retrieval_result.history_summary)
    messages = [*retrieval_result.history, ChatTurn(role="user", content=retrieval_result.prompt or "")]
    raw_answer = _strip_meta_references(await generator.generate(system, messages))
    policy = policy_gate.check(retrieval_result.query, raw_answer, has_context=bool(retrieval_result.hits))
    answer = raw_answer if policy.passed else _POLICY_BLOCKED_ANSWER

    return GenerationResult(
        query=retrieval_result.query,
        in_scope=True,
        route="in_scope",
        answer=answer,
        sources=retrieval_result.hits,
        policy=policy,
        history=_append_exchange(retrieval_result.history, retrieval_result.query, answer),
        history_summary=retrieval_result.history_summary,
    )


def _append_exchange(history: list[ChatTurn], query: str, answer: str) -> list[ChatTurn]:
    return [*history, ChatTurn(role="user", content=query), ChatTurn(role="assistant", content=answer)]
