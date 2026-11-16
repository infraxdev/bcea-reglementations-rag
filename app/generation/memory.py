from __future__ import annotations

from ..config import get_rewrite_settings
from ..retrieval.models import ChatTurn
from .interfaces import Generator
from .llm import build_generator

# 5 user/assistant exchanges kept verbatim before older ones get folded into the rolling
# summary. Must be even -- history always alternates starting on "user" (see
# generation/pipeline.py's _append_exchange), so an even-sized tail also starts on "user".
KEEP_TURNS = 10

_SUMMARY_SYSTEM = (
    "You maintain a running summary of a conversation between a user and a BCEAO/UEMOA "
    "banking-regulation assistant. Given the previous summary (if any) and the next "
    "exchange to fold in, write an updated, concise summary that preserves every fact, "
    "decision, and open question the user might still need to refer back to. Output "
    "ONLY the updated summary, in a few sentences, with no preamble or labels."
)


async def fold_history(
    history: list[ChatTurn],
    history_summary: str | None,
    generator: Generator | None = None,
    keep_turns: int = KEEP_TURNS,
) -> tuple[list[ChatTurn], str | None]:
    """Bounds the conversation history sent to the answer-generation LLM: keeps the last
    `keep_turns` turns verbatim and folds anything older into a rolling summary via one
    short LLM call. Because the API is stateless and the caller always resends the
    `history`/`history_summary` this returned last time (see api/query.py and
    GenerationResult), only the turn(s) that just aged out need folding in each call —
    not a full re-summarization from scratch."""
    if len(history) <= keep_turns:
        return history, history_summary

    overflow, kept = history[:-keep_turns], history[-keep_turns:]
    generator = generator or _build_summary_generator()

    exchange = "\n".join(f"{turn.role}: {turn.content}" for turn in overflow)
    user_content = (
        (f"Previous summary:\n{history_summary}\n\n" if history_summary else "")
        + f"New exchange to fold in:\n{exchange}"
    )
    updated = await generator.generate(_SUMMARY_SYSTEM, [ChatTurn(role="user", content=user_content)])
    return kept, updated.strip() or history_summary


def _build_summary_generator() -> Generator:
    # Deliberately the same low-latency "rewrite tier" model as retrieval/rewrite.py,
    # not GENERATION_PROVIDER -- this runs as extra overhead on top of every request once
    # a conversation is long enough to overflow keep_turns.
    settings = get_rewrite_settings()
    return build_generator(settings.provider, settings.model)
