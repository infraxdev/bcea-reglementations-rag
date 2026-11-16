"""Process bootstrap shared by the API (app/main.py) and the worker (app/worker.py)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent


def bootstrap() -> None:
    load_dotenv()
    # fastembed reads FASTEMBED_CACHE_PATH directly via os.getenv and resolves it against
    # the process's cwd at access time. Anchor a relative value to the repo root so the
    # multi-GB model cache is found regardless of where the process is started from
    # (otherwise a different cwd silently triggers a full re-download).
    cache_path = os.environ.get("FASTEMBED_CACHE_PATH")
    if cache_path and not Path(cache_path).is_absolute():
        os.environ["FASTEMBED_CACHE_PATH"] = str((_REPO_ROOT / cache_path).resolve())
