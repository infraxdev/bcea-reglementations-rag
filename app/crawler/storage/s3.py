from __future__ import annotations

import asyncio
from pathlib import Path

import boto3
from botocore.client import Config

from ...config import S3StorageSettings
from .base import StorageBackend


def build_s3_client(cfg: S3StorageSettings):
    """S3 client for the configured bucket. Shared by the crawler (uploads), the job
    manifest store (app/crawler/job_store.py) and ingestion (downloads + processed/ moves)."""
    session = boto3.session.Session(
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        region_name=cfg.region,
    )
    return session.client(
        "s3",
        endpoint_url=cfg.endpoint_url,
        use_ssl=cfg.use_ssl,
        config=Config(signature_version="s3v4"),
    )


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """'s3://bucket/a/b.pdf' -> ('bucket', 'a/b.pdf')."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an s3:// URI: {uri!r}")
    bucket, _, key = uri[len("s3://"):].partition("/")
    if not bucket or not key:
        raise ValueError(f"Malformed s3:// URI: {uri!r}")
    return bucket, key


class S3Storage(StorageBackend):
    """Works against real AWS S3 as well as S3-compatible services (MinIO, R2, etc.)
    via `endpoint_url`. Credentials fall back to the server's default AWS chain
    (env vars, ~/.aws/credentials, instance role) when not supplied explicitly."""

    def __init__(self, cfg: S3StorageSettings, job_id: str):
        self.bucket = cfg.bucket
        self.prefix = f"{cfg.prefix.strip('/')}/{job_id}" if cfg.prefix else job_id
        self.client = build_s3_client(cfg)

    def _full_key(self, key: str) -> str:
        return f"{self.prefix}/{key}"

    async def save_file(self, key: str, source_path: Path, content_type: str | None) -> str:
        full_key = self._full_key(key)
        extra_args = {"ContentType": content_type} if content_type else None
        await asyncio.to_thread(
            self.client.upload_file, str(source_path), self.bucket, full_key, ExtraArgs=extra_args
        )
        return f"s3://{self.bucket}/{full_key}"

    async def save_bytes(self, key: str, data: bytes, content_type: str | None) -> str:
        full_key = self._full_key(key)
        kwargs = {"Bucket": self.bucket, "Key": full_key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        await asyncio.to_thread(self.client.put_object, **kwargs)
        return f"s3://{self.bucket}/{full_key}"
