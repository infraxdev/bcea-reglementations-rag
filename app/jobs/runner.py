"""Runs one crawl/ingest job and records its outcome in the state stores.

Shared by both dispatch modes, so status/progress behave identically:
- inprocess: app/jobs/runtime.py calls execute() as an asyncio task in the API.
- sqs: app/worker.py calls execute() per received message and maps the returned
  Outcome onto SQS actions (delete, retry later, or leave for the DLQ).
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from pydantic import ValidationError

from ..config import (
    GenerationConfigError,
    QdrantConfigError,
    StorageConfigError,
    get_job_settings,
)
from ..crawler.engine import run_crawl
from ..crawler.job_store import load_job_result, save_job_result
from ..crawler.models import CrawlRequest
from ..ingestion import progress
from ..ingestion.pipeline import index_crawl_job
from . import state
from .models import JobMessage, JobType

log = logging.getLogger(__name__)


class PermanentJobError(Exception):
    """Retrying can't help (bad request, missing manifest, server misconfiguration)."""


# Exceptions that mean "fix the config or the request", not "try again later".
_PERMANENT = (PermanentJobError, ValidationError, StorageConfigError, QdrantConfigError, GenerationConfigError)


class Outcome(str, Enum):
    SUCCEEDED = "succeeded"
    DUPLICATE = "duplicate"  # another live worker already runs this job_id
    RETRY = "retry"  # failed; attempts remain
    FAILED_PERMANENT = "failed_permanent"  # failed; retrying is pointless
    FAILED_FINAL = "failed_final"  # failed on the last allowed attempt


def _running_elsewhere(msg: JobMessage) -> bool:
    if msg.type == JobType.CRAWL:
        current = state.get_crawl_status(msg.job_id)
    else:
        current = progress.get(msg.job_id)
    return current is not None and current.status == "running" and state.is_active(current.status, current.updated_at)


def _mark_running(msg: JobMessage, attempt: int) -> None:
    if msg.type == JobType.CRAWL:
        if state.get_crawl_status(msg.job_id) is None:  # submitted without the API (e.g. by hand)
            state.queue_crawl(msg.job_id, str((msg.request or {}).get("start_url", "")))
        state.update_crawl(msg.job_id, status="running", attempts=attempt)
    else:
        if progress.get(msg.job_id) is None:
            progress.queue(msg.job_id)
        progress.update(msg.job_id, status="running", attempts=attempt)


def _mark_failed(msg: JobMessage, error: str, final: bool) -> None:
    status = "failed" if final else "queued"
    if msg.type == JobType.CRAWL:
        state.update_crawl(msg.job_id, status=status, error=error)
    else:
        current = progress.get(msg.job_id)
        errors = [*(current.errors if current else []), error]
        progress.update(msg.job_id, status=status, errors=errors, current_file=None)


def _touch(msg: JobMessage) -> None:
    if msg.type == JobType.CRAWL:
        state.touch_crawl(msg.job_id)
    else:
        progress.touch(msg.job_id)


async def _heartbeat(msg: JobMessage, every: float) -> None:
    while True:
        await asyncio.sleep(every)
        try:
            _touch(msg)
        except Exception:  # a missed heartbeat must never kill the job itself
            log.warning("heartbeat failed for %s job %s", msg.type.value, msg.job_id, exc_info=True)


async def _run_crawl(msg: JobMessage) -> None:
    req = CrawlRequest.model_validate({**(msg.request or {}), "job_id": msg.job_id})
    result = await run_crawl(req)
    await asyncio.to_thread(save_job_result, result)
    state.update_crawl(
        msg.job_id,
        status=result.status,
        error=None,
        resources_downloaded=result.stats.resources_downloaded,
        resources_failed=result.stats.resources_failed,
    )


async def _run_ingest(msg: JobMessage) -> None:
    if await asyncio.to_thread(load_job_result, msg.job_id) is None:
        raise PermanentJobError(f"No crawl manifest found for job_id={msg.job_id!r}")
    await index_crawl_job(msg.job_id)  # sets progress status="completed" itself


async def execute(msg: JobMessage, attempt: int, max_attempts: int) -> Outcome:
    if _running_elsewhere(msg):
        log.info("%s job %s is already running on a live worker; dropping duplicate", msg.type.value, msg.job_id)
        return Outcome.DUPLICATE

    log.info("starting %s job %s (attempt %d/%d)", msg.type.value, msg.job_id, attempt, max_attempts)
    _mark_running(msg, attempt)
    heartbeat = asyncio.create_task(_heartbeat(msg, get_job_settings().heartbeat_seconds))
    try:
        if msg.type == JobType.CRAWL:
            await _run_crawl(msg)
        else:
            await _run_ingest(msg)
    except asyncio.CancelledError:
        # Worker shutting down (SIGTERM, Spot reclaim): hand the job back. Both pipelines
        # resume where they stopped, so the next attempt doesn't redo finished work.
        _mark_failed(msg, f"attempt {attempt}: interrupted by worker shutdown; will retry", final=False)
        raise
    except Exception as exc:
        permanent = isinstance(exc, _PERMANENT)
        final = permanent or attempt >= max_attempts
        message = f"attempt {attempt}: {exc or type(exc).__name__}"
        _mark_failed(msg, message, final=final)
        log.exception("%s job %s failed (%s)", msg.type.value, msg.job_id, "final" if final else "will retry")
        if permanent:
            return Outcome.FAILED_PERMANENT
        return Outcome.FAILED_FINAL if final else Outcome.RETRY
    finally:
        heartbeat.cancel()

    log.info("%s job %s succeeded", msg.type.value, msg.job_id)
    return Outcome.SUCCEEDED
