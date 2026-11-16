from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import GenerationConfigError, QdrantConfigError
from ..generation.llm import build_generator
from ..generation.memory import fold_history
from ..generation.models import GenerationResult
from ..generation.pipeline import generate_answer
from ..retrieval.models import ChatTurn
from ..retrieval.pipeline import retrieve

router = APIRouter(tags=["query"])

class QueryRequest(BaseModel):
    query: str
    # Prior turns, oldest first -- used by the query rewriter to resolve pronouns and
    # implicit references ("it", "this article") in `query`, and fed to the
    # answer-generation LLM as real conversation turns. The API is stateless: the caller
    # owns conversation history and resends it each request -- but should resend exactly
    # what the previous response's `history` field contained (already capped), not the
    # full on-screen transcript. See generation/memory.py.
    history: list[ChatTurn] | None = None
    # Rolling summary of everything older than `history`, from the previous response's
    # `history_summary`. None on the first turn of a conversation.
    history_summary: str | None = None
    # Optional per-request overrides of GENERATION_PROVIDER/GENERATION_MODEL — lets a
    # caller A/B Qwen (ollama) vs. ChatGPT (openai) vs. Claude (anthropic) without
    # restarting the server. Omit both to use the server's configured default.
    provider: str | None = None
    model: str | None = None


@router.post("/query", response_model=GenerationResult)
async def query(req: QueryRequest) -> GenerationResult:
    """Retrieval · online + Generation, end to end: cap/fold history -> query router
    (one LLM call: scope + rewritten query, or the reply returned as-is for small talk /
    out-of-scope messages; general finance questions skip straight to the generation
    LLM with the history and no retrieval) -> hybrid search -> rerank ->
    prompt assembly -> LLM (system prompt + multi-turn messages) -> policy gate ->
    response. Raises 501 once execution reaches a pipeline stage that isn't configured
    yet (Qdrant / embedder / reranker / generation LLM — see retrieval/*.py,
    generation/llm.py, and .env.example)."""
    try:
        kept_history, history_summary = await fold_history(req.history or [], req.history_summary)
        retrieval_result = await retrieve(req.query, history=kept_history, history_summary=history_summary)
        generator = build_generator(req.provider, req.model) if (req.provider or req.model) else None
        return await generate_answer(retrieval_result, generator=generator)
    except (NotImplementedError, QdrantConfigError, GenerationConfigError) as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
