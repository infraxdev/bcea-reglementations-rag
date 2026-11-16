"""Crawl job status (jobs table) plus the shared 'is this job still alive?' rule."""

from __future__ import annotations

import time

from ..config import get_job_settings
from .kv import get_store
from .models import ACTIVE_STATUSES, CrawlJobStatus


def is_active(status: str, updated_at: float) -> bool:
    """queued/running AND touched recently. A worker heartbeats every
    JOB_HEARTBEAT_SECONDS while it runs a job, so a record that has gone quiet for
    JOB_STALE_SECONDS belongs to a dead worker and may be re-submitted."""
    if status not in ACTIVE_STATUSES:
        return False
    return time.time() - updated_at < get_job_settings().stale_after_seconds


def get_crawl_status(job_id: str) -> CrawlJobStatus | None:
    raw = get_store("jobs").get(job_id)
    return CrawlJobStatus.model_validate(raw) if raw is not None else None


def queue_crawl(job_id: str, start_url: str) -> CrawlJobStatus:
    now = time.time()
    status = CrawlJobStatus(job_id=job_id, status="queued", start_url=start_url, submitted_at=now, updated_at=now)
    get_store("jobs").put(job_id, status.model_dump(mode="json"))
    return status


def update_crawl(job_id: str, **fields: object) -> None:
    current = get_crawl_status(job_id)
    if current is None:
        return
    updated = current.model_copy(update={**fields, "updated_at": time.time()})
    get_store("jobs").put(job_id, updated.model_dump(mode="json"))


def touch_crawl(job_id: str) -> None:
    update_crawl(job_id)
