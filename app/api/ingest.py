from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import QdrantConfigError
from ..ingestion.models import IndexResult
from ..ingestion.pipeline import index_crawl_job

router = APIRouter(tags=["ingest"])


@router.post("/ingest/{job_id}", response_model=IndexResult)
async def ingest(job_id: str) -> IndexResult:
    """Runs Parse -> VLM normalize -> Chunk -> Embed -> Qdrant for every downloaded
    resource in a completed crawl job. Raises 501 once execution reaches a pipeline
    stage that isn't configured yet (Qdrant / VLM normalizer / embedder — see
    ingestion/*.py and .env.example)."""
    try:
        return await index_crawl_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NotImplementedError, QdrantConfigError) as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
