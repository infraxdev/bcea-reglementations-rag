from __future__ import annotations

from functools import lru_cache

from ..config import get_job_settings
from .models import JobType


@lru_cache(maxsize=1)
def sqs_client():
    import boto3

    settings = get_job_settings()
    return boto3.client("sqs", endpoint_url=settings.sqs_endpoint_url, region_name=settings.aws_region)


def queue_url_for(job_type: JobType) -> str:
    settings = get_job_settings()
    url = settings.crawl_queue_url if job_type == JobType.CRAWL else settings.ingest_queue_url
    assert url, "validated by get_job_settings() when JOB_QUEUE_BACKEND=sqs"
    return url
