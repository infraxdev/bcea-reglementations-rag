from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from .base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str, job_id: str):
        self.root = Path(base_dir).expanduser().resolve() / job_id
        self.root.mkdir(parents=True, exist_ok=True)

    def _dest(self, key: str) -> Path:
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    async def save_file(self, key: str, source_path: Path, content_type: str | None) -> str:
        dest = self._dest(key)
        await asyncio.to_thread(shutil.copyfile, str(source_path), str(dest))
        return str(dest)

    async def save_bytes(self, key: str, data: bytes, content_type: str | None) -> str:
        dest = self._dest(key)
        await asyncio.to_thread(dest.write_bytes, data)
        return str(dest)
