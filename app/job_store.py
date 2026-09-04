from __future__ import annotations

from pathlib import Path

from .models import CrawlResult

JOB_METADATA_DIR = Path("job_metadata")
JOB_METADATA_DIR.mkdir(parents=True, exist_ok=True)


def save_job_result(result: CrawlResult) -> Path:
    """Persists the manifest locally (regardless of where the actual resource
    files were stored) so a job's results can be looked up again later."""
    path = JOB_METADATA_DIR / f"{result.job_id}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_job_result(job_id: str) -> CrawlResult | None:
    path = JOB_METADATA_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return CrawlResult.model_validate_json(path.read_text(encoding="utf-8"))


def list_jobs() -> list[str]:
    return sorted(p.stem for p in JOB_METADATA_DIR.glob("*.json"))
