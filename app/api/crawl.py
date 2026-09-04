from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import StorageConfigError
from ..crawler.engine import run_crawl
from ..crawler.job_store import list_jobs, load_job_result, save_job_result
from ..crawler.models import CrawlRequest, CrawlResult

router = APIRouter(tags=["crawl"])


@router.post("/crawl", response_model=CrawlResult)
async def crawl(req: CrawlRequest) -> CrawlResult:
    """Runs the crawl synchronously and returns the full manifest once finished.
    For a large site this can take a while — tune max_pages/max_depth/timeout_seconds
    to bound the request duration."""
    try:
        result = await run_crawl(req)
    except StorageConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    save_job_result(result)
    return result


@router.get("/jobs", response_model=list[str])
async def jobs() -> list[str]:
    return list_jobs()


@router.get("/jobs/{job_id}", response_model=CrawlResult)
async def job(job_id: str) -> CrawlResult:
    result = load_job_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="job not found")
    return result
