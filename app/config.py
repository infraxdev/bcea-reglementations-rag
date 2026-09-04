from __future__ import annotations

import os
from dataclasses import dataclass


class StorageConfigError(RuntimeError):
    """Raised when the requested storage backend isn't configured on the server."""


class QdrantConfigError(RuntimeError):
    """Raised when Qdrant isn't configured on the server."""


@dataclass(frozen=True)
class LocalStorageSettings:
    base_dir: str


@dataclass(frozen=True)
class S3StorageSettings:
    bucket: str
    endpoint_url: str | None
    region: str | None
    access_key: str | None
    secret_key: str | None
    prefix: str
    use_ssl: bool


@dataclass(frozen=True)
class QdrantSettings:
    url: str
    api_key: str | None
    collection: str


def get_qdrant_settings() -> QdrantSettings:
    url = os.environ.get("QDRANT_URL")
    if not url:
        raise QdrantConfigError(
            "QDRANT_URL is not set on the server. Configure QDRANT_URL (and optionally "
            "QDRANT_API_KEY, QDRANT_COLLECTION) as environment variables."
        )
    return QdrantSettings(
        url=url,
        api_key=os.environ.get("QDRANT_API_KEY") or None,
        collection=os.environ.get("QDRANT_COLLECTION", "bceao_regulations"),
    )


def get_local_storage_settings() -> LocalStorageSettings:
    return LocalStorageSettings(base_dir=os.environ.get("LOCAL_STORAGE_BASE_DIR", "data"))


def get_s3_storage_settings() -> S3StorageSettings:
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise StorageConfigError(
            "storage_backend='s3' but S3_BUCKET is not set on the server. "
            "Configure S3_BUCKET (and optionally S3_ENDPOINT_URL, S3_REGION, "
            "S3_ACCESS_KEY, S3_SECRET_KEY, S3_PREFIX, S3_USE_SSL) as environment variables."
        )
    use_ssl_raw = os.environ.get("S3_USE_SSL", "true").strip().lower()
    return S3StorageSettings(
        bucket=bucket,
        endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
        region=os.environ.get("S3_REGION", "us-east-1"),
        access_key=os.environ.get("S3_ACCESS_KEY") or None,
        secret_key=os.environ.get("S3_SECRET_KEY") or None,
        prefix=os.environ.get("S3_PREFIX", ""),
        use_ssl=use_ssl_raw not in ("0", "false", "no"),
    )
