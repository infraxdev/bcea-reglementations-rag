from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ..config import StorageConfigError, get_s3_storage_settings
from ..crawler.job_store import list_jobs, load_job_result
from ..crawler.models import CrawlRequest, CrawlResult
from ..jobs import runtime, state
from ..jobs.models import CrawlJobStatus, JobAccepted, JobMessage, JobType

router = APIRouter(tags=["crawl"])


@router.post("/crawl", response_model=JobAccepted, status_code=202)
async def crawl(req: CrawlRequest) -> JobAccepted:
    """Queues the crawl and returns immediately. Poll GET /crawl/{job_id}/status; once it
    reports completed, the full manifest is at GET /jobs/{job_id} and the job can be
    indexed with POST /ingest/{job_id}.

    With JOB_QUEUE_BACKEND=sqs a worker pod runs it (retried up to JOB_MAX_ATTEMPTS
    times); with the default inprocess backend this API process runs it in the background."""
    if req.storage_backend == "s3":
        try:
            get_s3_storage_settings()  # reject now rather than fail inside a worker later
        except StorageConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = req.job_id or uuid4().hex
    current = await asyncio.to_thread(state.get_crawl_status, job_id)
    if current is not None and state.is_active(current.status, current.updated_at):
        raise HTTPException(status_code=409, detail=f"Crawl job {job_id!r} is already {current.status}.")

    await asyncio.to_thread(state.queue_crawl, job_id, str(req.start_url))
    msg = JobMessage(type=JobType.CRAWL, job_id=job_id, request=req.model_dump(mode="json", exclude={"job_id"}))
    try:
        await runtime.submit(msg)
    except Exception as exc:
        await asyncio.to_thread(state.update_crawl, job_id, status="failed", error=f"could not enqueue: {exc}")
        raise HTTPException(status_code=503, detail=f"Could not queue the crawl job: {exc}") from exc
    return JobAccepted(job_id=job_id, status_url=f"/crawl/{job_id}/status")


@router.get("/crawl/{job_id}/status", response_model=CrawlJobStatus)
async def crawl_status(job_id: str) -> CrawlJobStatus:
    current = await asyncio.to_thread(state.get_crawl_status, job_id)
    if current is not None:
        return current
    # Crawls finished before job tracking existed only have a manifest.
    manifest = await asyncio.to_thread(load_job_result, job_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"No crawl job found for job_id={job_id!r}")
    now = time.time()
    return CrawlJobStatus(
        job_id=job_id,
        status=manifest.status,
        start_url=manifest.start_url,
        resources_downloaded=manifest.stats.resources_downloaded,
        resources_failed=manifest.stats.resources_failed,
        submitted_at=now,
        updated_at=now,
    )


@router.get("/jobs", response_model=list[str])
async def jobs() -> list[str]:
    """Ids of crawls that have finished (i.e. have a manifest)."""
    return await asyncio.to_thread(list_jobs)


@router.get("/jobs/{job_id}", response_model=CrawlResult)
async def job(job_id: str) -> CrawlResult:
    result = await asyncio.to_thread(load_job_result, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="job not found (or the crawl hasn't finished yet)")
    return result
