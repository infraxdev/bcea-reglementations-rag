from __future__ import annotations

from ...config import get_local_storage_settings, get_s3_storage_settings
from .base import StorageBackend
from .local import LocalStorage
from .s3 import S3Storage

__all__ = ["StorageBackend", "LocalStorage", "S3Storage", "build_storage"]


def build_storage(backend: str, job_id: str) -> StorageBackend:
    if backend == "local":
        settings = get_local_storage_settings()
        return LocalStorage(settings.base_dir, job_id)
    if backend == "s3":
        settings = get_s3_storage_settings()
        return S3Storage(settings, job_id)
    raise ValueError(f"Unsupported storage backend: {backend}")
