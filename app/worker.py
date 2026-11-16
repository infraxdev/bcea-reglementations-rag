"""Job worker: `python -m app.worker`.

Long-polls the crawl and ingest SQS queues and runs each job with app/jobs/runner.py,
the same code the API uses in inprocess mode. Runs as the `worker` Deployment on EKS
(KEDA scales it from 0 on queue depth) and as the `worker` service in compose.yml
(against ElasticMQ). Needs JOB_QUEUE_BACKEND=sqs and JOB_STATE_BACKEND=dynamodb.

Message lifecycle:
- received -> run; a heartbeat keeps extending the message's visibility timeout, so
  SQS doesn't hand it to another worker while this one is still busy;
- success, duplicate, or permanent failure -> message deleted;
- retryable failure -> message made visible again after a backoff; after
  JOB_MAX_ATTEMPTS receives, SQS moves it to the dead-letter queue;
- SIGTERM (deploy, scale-in, Spot reclaim) -> stop receiving, cancel the running job and
  release its message immediately so another worker resumes it.

Each queue gets its own consumer handling one message at a time. A pod can therefore
crawl (network-bound) and ingest (CPU/memory-bound) at once, but never runs two ingests
at once. Scale out with more pods, not more concurrency per pod.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket

from pydantic import ValidationError

from .env import bootstrap

bootstrap()

from .config import get_job_settings
from .jobs.models import JobMessage, JobType
from .jobs.runner import Outcome, execute
from .jobs.sqs import queue_url_for, sqs_client

log = logging.getLogger("app.worker")

_RECEIVE_WAIT_SECONDS = 20  # SQS long-poll maximum


class Worker:
    def __init__(self) -> None:
        self.settings = get_job_settings()
        if self.settings.queue_backend != "sqs":
            raise SystemExit("app.worker needs JOB_QUEUE_BACKEND=sqs (with the inprocess backend the API runs jobs itself).")
        self.sqs = sqs_client()
        self.stopping = asyncio.Event()

    async def _call(self, fn, /, **kwargs):
        return await asyncio.to_thread(fn, **kwargs)

    async def _set_visibility(self, queue_url: str, receipt: str, seconds: int) -> None:
        try:
            await self._call(
                self.sqs.change_message_visibility,
                QueueUrl=queue_url,
                ReceiptHandle=receipt,
                VisibilityTimeout=seconds,
            )
        except Exception:
            log.warning("could not change message visibility", exc_info=True)

    async def _keep_invisible(self, queue_url: str, receipt: str) -> None:
        while True:
            await asyncio.sleep(self.settings.heartbeat_seconds)
            await self._set_visibility(queue_url, receipt, self.settings.visibility_timeout_seconds)

    async def _handle(self, queue_url: str, message: dict) -> None:
        receipt = message["ReceiptHandle"]
        attempt = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
        try:
            job = JobMessage.model_validate_json(message["Body"])
        except ValidationError:
            log.error("dropping malformed message %s: %r", message.get("MessageId"), message.get("Body"))
            await self._call(self.sqs.delete_message, QueueUrl=queue_url, ReceiptHandle=receipt)
            return

        # Start with a full visibility window; the heartbeat keeps it there.
        await self._set_visibility(queue_url, receipt, self.settings.visibility_timeout_seconds)
        keep_invisible = asyncio.create_task(self._keep_invisible(queue_url, receipt))
        run = asyncio.create_task(execute(job, attempt=attempt, max_attempts=self.settings.max_attempts))
        stop = asyncio.create_task(self.stopping.wait())
        try:
            await asyncio.wait({run, stop}, return_when=asyncio.FIRST_COMPLETED)
            if not run.done():
                log.info("shutting down: releasing %s job %s for another worker", job.type.value, job.job_id)
                run.cancel()
                await asyncio.gather(run, return_exceptions=True)
                await self._set_visibility(queue_url, receipt, 0)
                return
            outcome = run.result()
        except Exception:
            # execute() records job failures itself; getting here means the state store
            # itself failed. Leave the message to reappear after its visibility timeout.
            log.exception("unexpected error running %s job %s", job.type.value, job.job_id)
            return
        finally:
            keep_invisible.cancel()
            stop.cancel()

        if outcome in (Outcome.SUCCEEDED, Outcome.DUPLICATE, Outcome.FAILED_PERMANENT):
            await self._call(self.sqs.delete_message, QueueUrl=queue_url, ReceiptHandle=receipt)
        elif outcome == Outcome.RETRY:
            await self._set_visibility(queue_url, receipt, self.settings.retry_backoff_seconds * attempt)
        else:  # FAILED_FINAL: let it reappear once more so SQS moves it to the DLQ
            await self._set_visibility(queue_url, receipt, 0)

    async def consume(self, job_type: JobType) -> None:
        queue_url = queue_url_for(job_type)
        log.info("consuming %s jobs from %s", job_type.value, queue_url)
        while not self.stopping.is_set():
            try:
                resp = await self._call(
                    self.sqs.receive_message,
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=_RECEIVE_WAIT_SECONDS,
                    AttributeNames=["ApproximateReceiveCount"],
                )
            except Exception:
                log.exception("receive from %s failed; retrying in 5s", job_type.value)
                await asyncio.sleep(5)
                continue
            for message in resp.get("Messages", []):
                if self.stopping.is_set():
                    await self._set_visibility(queue_url, message["ReceiptHandle"], 0)
                    continue
                await self._handle(queue_url, message)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self.stopping.set)
        log.info("worker %s started", socket.gethostname())
        await asyncio.gather(self.consume(JobType.INGEST), self.consume(JobType.CRAWL))
        log.info("worker stopped")


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(Worker().run())


if __name__ == "__main__":
    main()
