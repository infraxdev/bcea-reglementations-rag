from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from ..crawler.job_store import load_job_result
from ..ingestion import progress as progress_store
from ..ingestion.models import IngestProgress
from ..jobs import runtime, state
from ..jobs.models import JobAccepted, JobMessage, JobType

router = APIRouter(tags=["ingest"])


@router.post("/ingest/{job_id}", response_model=JobAccepted, status_code=202)
async def ingest(job_id: str) -> JobAccepted:
    """Queues Parse -> VLM normalize -> Chunk -> Embed -> Qdrant -> move to processed/
    for every not-yet-processed downloaded resource in a completed crawl job, and returns
    immediately. Poll GET /ingest/{job_id}/progress for live status (docs/sec, ETA,
    current file — see ingestion/models.py:IngestProgress).

    Safe to re-run on a job that already partially completed: files already moved into
    processed/ are skipped rather than reprocessed. That's also what makes worker retries
    after a crash cheap."""
    if await asyncio.to_thread(load_job_result, job_id) is None:
        raise HTTPException(status_code=404, detail=f"No completed crawl job found for job_id={job_id!r}")
    current = await asyncio.to_thread(progress_store.get, job_id)
    if current is not None and state.is_active(current.status, current.updated_at):
        raise HTTPException(status_code=409, detail=f"Ingest job {job_id!r} is already {current.status}.")

    await asyncio.to_thread(progress_store.queue, job_id)
    try:
        await runtime.submit(JobMessage(type=JobType.INGEST, job_id=job_id))
    except Exception as exc:
        await asyncio.to_thread(
            progress_store.update, job_id, status="failed", errors=[f"could not enqueue: {exc}"]
        )
        raise HTTPException(status_code=503, detail=f"Could not queue the ingest job: {exc}") from exc
    return JobAccepted(job_id=job_id, status_url=f"/ingest/{job_id}/progress")


@router.get("/ingest/{job_id}/progress", response_model=IngestProgress)
async def ingest_progress(job_id: str) -> IngestProgress:
    progress = await asyncio.to_thread(progress_store.get, job_id)
    if progress is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ingest run found for job_id={job_id!r}. Start one with POST /ingest/{job_id}.",
        )
    return progress
