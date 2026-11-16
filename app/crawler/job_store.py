"""Crawl manifests (CrawlResult JSON), one per job.

JOB_MANIFEST_BACKEND=local (default): job_metadata/<job_id>.json on this machine's disk.
Works for plain uvicorn and for compose.yml, where api and worker mount the same volume.

JOB_MANIFEST_BACKEND=s3: s3://$S3_BUCKET/$S3_PREFIX/job_metadata/<job_id>.json. Needed
on EKS, where the worker pod that writes a manifest and the API/worker pods that later
read it share no disk. (Manifests can run to megabytes for big crawls, which is why they
go to S3 rather than into the DynamoDB jobs table, whose items max out at 400 KB.)
"""

from __future__ import annotations

from pathlib import Path

from ..config import get_job_settings, get_s3_storage_settings
from .models import CrawlResult

JOB_METADATA_DIR = Path("job_metadata")
_S3_DIRNAME = "job_metadata"


def _s3():
    from .storage.s3 import build_s3_client

    cfg = get_s3_storage_settings()
    prefix = f"{cfg.prefix.strip('/')}/{_S3_DIRNAME}/" if cfg.prefix.strip("/") else f"{_S3_DIRNAME}/"
    return build_s3_client(cfg), cfg.bucket, prefix


def _use_s3() -> bool:
    return get_job_settings().manifest_backend == "s3"


def save_job_result(result: CrawlResult) -> str:
    """Returns where the manifest was written (path or s3:// URI)."""
    body = result.model_dump_json(indent=2)
    if _use_s3():
        client, bucket, prefix = _s3()
        key = f"{prefix}{result.job_id}.json"
        client.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"), ContentType="application/json")
        return f"s3://{bucket}/{key}"
    JOB_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    path = JOB_METADATA_DIR / f"{result.job_id}.json"
    path.write_text(body, encoding="utf-8")
    return str(path)


def load_job_result(job_id: str) -> CrawlResult | None:
    if _use_s3():
        client, bucket, prefix = _s3()
        try:
            obj = client.get_object(Bucket=bucket, Key=f"{prefix}{job_id}.json")
        except client.exceptions.NoSuchKey:
            return None
        return CrawlResult.model_validate_json(obj["Body"].read())
    path = JOB_METADATA_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return CrawlResult.model_validate_json(path.read_text(encoding="utf-8"))


def list_jobs() -> list[str]:
    if _use_s3():
        client, bucket, prefix = _s3()
        ids: list[str] = []
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                name = obj["Key"][len(prefix):]
                if name.endswith(".json") and "/" not in name:
                    ids.append(name[: -len(".json")])
        return sorted(ids)
    if not JOB_METADATA_DIR.exists():
        return []
    return sorted(p.stem for p in JOB_METADATA_DIR.glob("*.json"))
