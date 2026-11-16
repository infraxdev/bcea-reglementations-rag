"""Live progress of ingest runs, keyed by job_id (GET /ingest/{job_id}/progress).

Backed by app/jobs/kv.py: an in-process dict with JOB_STATE_BACKEND=memory, or the
DynamoDB job-progress table with JOB_STATE_BACKEND=dynamodb. That way the worker pod
running the ingest and whichever API replica answers the poll see the same record.
"""

from __future__ import annotations

import time

from ..jobs.kv import get_store
from .models import IngestProgress

# DynamoDB items max out at 400 KB. A crawl with thousands of unparseable files could
# exceed that through `errors` alone, so only the most recent ones are kept here (the
# full list is still in the IndexResult returned by the pipeline and in worker logs).
_MAX_STORED_ERRORS = 300


def _save(progress: IngestProgress) -> IngestProgress:
    get_store("progress").put(progress.job_id, progress.model_dump(mode="json"))
    return progress


def _cap_errors(errors: list[str]) -> list[str]:
    if len(errors) <= _MAX_STORED_ERRORS:
        return errors
    dropped = len(errors) - (_MAX_STORED_ERRORS - 1)
    return [f"[{dropped} earlier errors not shown]", *errors[-(_MAX_STORED_ERRORS - 1):]]


def get(job_id: str) -> IngestProgress | None:
    raw = get_store("progress").get(job_id)
    if raw is None:
        return None
    # Drop computed fields (documents_done, rate, eta) that model_dump included.
    fields = set(IngestProgress.model_fields)
    return IngestProgress.model_validate({k: v for k, v in raw.items() if k in fields})


def queue(job_id: str) -> IngestProgress:
    """Called by the API when it submits the job, before a worker picks it up."""
    now = time.time()
    return _save(IngestProgress(job_id=job_id, status="queued", total_documents=0, started_at=now, updated_at=now))


def start(job_id: str, total_documents: int, documents_skipped: int = 0) -> IngestProgress:
    now = time.time()
    previous = get(job_id)
    return _save(
        IngestProgress(
            job_id=job_id,
            status="running",
            attempts=previous.attempts if previous else 0,
            total_documents=total_documents,
            documents_skipped=documents_skipped,
            started_at=now,
            updated_at=now,
        )
    )


def update(job_id: str, **fields: object) -> None:
    progress = get(job_id)
    if progress is None:
        return
    if "errors" in fields:
        fields["errors"] = _cap_errors(list(fields["errors"]))  # type: ignore[arg-type]
    _save(progress.model_copy(update={**fields, "updated_at": time.time()}))


def touch(job_id: str) -> None:
    """Heartbeat from app/jobs/runner.py: proves the job is still alive even while a
    single large document keeps the pipeline from reporting anything for a while."""
    update(job_id)
