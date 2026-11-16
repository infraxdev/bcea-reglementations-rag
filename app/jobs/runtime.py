"""API-side job submission (POST /crawl, POST /ingest/{job_id})."""

from __future__ import annotations

import asyncio

from ..config import get_job_settings
from .models import JobMessage
from .runner import execute
from .sqs import queue_url_for, sqs_client

# Strong references to in-process tasks: asyncio only keeps weak ones, so an
# un-referenced task can be garbage-collected mid-run.
_tasks: set[asyncio.Task] = set()


async def submit(msg: JobMessage) -> None:
    settings = get_job_settings()
    if settings.queue_backend == "inprocess":
        # No queue to redeliver from, so one attempt only.
        task = asyncio.create_task(execute(msg, attempt=1, max_attempts=1))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return
    await asyncio.to_thread(
        sqs_client().send_message,
        QueueUrl=queue_url_for(msg.type),
        MessageBody=msg.model_dump_json(),
    )


async def shutdown() -> None:
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
