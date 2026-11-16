from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class JobType(str, Enum):
    CRAWL = "crawl"
    INGEST = "ingest"


class JobMessage(BaseModel):
    """Body of an SQS message (or an in-process submission)."""

    type: JobType
    job_id: str
    # CrawlRequest as JSON, for crawl jobs only.
    request: dict | None = None


# Statuses a job can be in while it still occupies its job_id.
ACTIVE_STATUSES = frozenset({"queued", "running"})


class CrawlJobStatus(BaseModel):
    """Lifecycle of a crawl job, stored in the jobs table (GET /crawl/{job_id}/status).
    The full manifest only exists once the crawl finishes (GET /jobs/{job_id})."""

    job_id: str
    status: Literal["queued", "running", "completed", "completed_with_errors", "failed"]
    start_url: str
    attempts: int = Field(0, description="How many times a worker has started this job.")
    error: str | None = Field(None, description="Last failure, if any (kept while a retry is pending).")
    resources_downloaded: int | None = None
    resources_failed: int | None = None
    submitted_at: float
    updated_at: float


class JobAccepted(BaseModel):
    job_id: str
    status: str = "queued"
    status_url: str
