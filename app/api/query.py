from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import QdrantConfigError
from ..generation.models import GenerationResult
from ..generation.pipeline import generate_answer
from ..retrieval.pipeline import retrieve

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    query: str


@router.post("/query", response_model=GenerationResult)
async def query(req: QueryRequest) -> GenerationResult:
    """Retrieval · online + Generation, end to end: query router -> (refused here, no LLM
    call, if out of scope) -> rewrite -> hybrid search -> rerank -> prompt assembly -> LLM
    -> policy gate -> response. Raises 501 once execution reaches a pipeline stage that
    isn't configured yet (Qdrant / embedder / reranker / generation LLM — see
    retrieval/*.py, generation/llm.py, and .env.example)."""
    try:
        retrieval_result = await retrieve(req.query)
        return await generate_answer(retrieval_result)
    except (NotImplementedError, QdrantConfigError) as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
