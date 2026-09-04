from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    @abstractmethod
    async def save_file(self, key: str, source_path: Path, content_type: str | None) -> str:
        """Persist an on-disk file under `key`. Returns a location string (path or URI)."""

    @abstractmethod
    async def save_bytes(self, key: str, data: bytes, content_type: str | None) -> str:
        """Persist in-memory bytes under `key`. Returns a location string (path or URI)."""
