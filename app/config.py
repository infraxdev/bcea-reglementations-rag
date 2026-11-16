from __future__ import annotations

import os
from dataclasses import dataclass


class StorageConfigError(RuntimeError):
    """Raised when the requested storage backend isn't configured on the server."""


class QdrantConfigError(RuntimeError):
    """Raised when Qdrant isn't configured on the server."""


class GenerationConfigError(RuntimeError):
    """Raised when the requested generation provider isn't configured on the server."""


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


@dataclass(frozen=True)
class GenerationSettings:
    provider: str
    model: str | None
    ollama_base_url: str
    openai_api_key: str | None
    anthropic_api_key: str | None


@dataclass(frozen=True)
class RewriteSettings:
    provider: str
    model: str | None


@dataclass(frozen=True)
class RouterSettings:
    provider: str
    model: str | None


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


def get_generation_settings() -> GenerationSettings:
    # OLLAMA_BASE_URL defaults to localhost for local dev; override it to point at an
    # in-cluster Ollama Service (e.g. a ClusterIP DNS name) when deployed to EKS.
    return GenerationSettings(
        provider=os.environ.get("GENERATION_PROVIDER", "ollama").strip().lower(),
        model=os.environ.get("GENERATION_MODEL") or None,
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
    )


def get_rewrite_settings() -> RewriteSettings:
    # Deliberately separate from GENERATION_PROVIDER — query rewriting benefits more
    # from low latency than from the strongest available model, so it defaults to the
    # local Ollama/Qwen path regardless of which provider answers the final question.
    # Only used when the scope router didn't already supply the rewritten query.
    return RewriteSettings(
        provider=os.environ.get("REWRITE_PROVIDER", "ollama").strip().lower(),
        model=os.environ.get("REWRITE_MODEL") or None,
    )


def get_router_settings() -> RouterSettings:
    # Deliberately separate from GENERATION_PROVIDER, like REWRITE_PROVIDER above: this
    # runs once on every message (scope decision + rewritten query or user-facing reply,
    # see retrieval/router.py's LLMScopeRouter), so it favors a fast local model over
    # the strongest available one.
    return RouterSettings(
        provider=os.environ.get("ROUTER_PROVIDER", "ollama").strip().lower(),
        model=os.environ.get("ROUTER_MODEL") or None,
    )


def get_cors_allowed_origins() -> list[str]:
    # Defaults to the Next.js dev server so the web/ interface works out of the box
    # locally; override with a comma-separated list for other environments (e.g. a
    # deployed frontend origin).
    raw = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


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


class JobConfigError(RuntimeError):
    """Raised when the job queue / job state backends are misconfigured."""


@dataclass(frozen=True)
class JobSettings:
    """How crawl/ingest jobs are dispatched and tracked (app/jobs/).

    - queue_backend "inprocess": the API runs jobs itself as asyncio tasks (plain
      `uvicorn` locally, no extra services). "sqs": the API enqueues to SQS and
      `python -m app.worker` pods consume (EKS, or ElasticMQ in compose.yml).
    - state_backend "memory": job status/progress live in the API process (only valid
      with "inprocess"). "dynamodb": shared tables that the API and workers both read
      and write (DynamoDB Local in compose.yml).
    - manifest_backend: where crawl manifests (CrawlResult JSON) are kept. "local" =
      job_metadata/ on disk (shared volume in compose.yml); "s3" = S3_BUCKET under
      job_metadata/ (EKS, where api and worker pods share no disk).
    """

    queue_backend: str
    aws_region: str | None
    crawl_queue_url: str | None
    ingest_queue_url: str | None
    sqs_endpoint_url: str | None
    state_backend: str
    jobs_table: str
    progress_table: str
    dynamodb_endpoint_url: str | None
    create_tables: bool
    manifest_backend: str
    max_attempts: int
    stale_after_seconds: float
    heartbeat_seconds: float
    visibility_timeout_seconds: int
    retry_backoff_seconds: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no")


def get_job_settings() -> JobSettings:
    settings = JobSettings(
        queue_backend=os.environ.get("JOB_QUEUE_BACKEND", "inprocess").strip().lower(),
        # Older botocore only reads AWS_DEFAULT_REGION, so resolve it here and pass it on.
        aws_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or None,
        crawl_queue_url=os.environ.get("CRAWL_JOBS_QUEUE_URL") or None,
        ingest_queue_url=os.environ.get("INGEST_JOBS_QUEUE_URL") or None,
        sqs_endpoint_url=os.environ.get("SQS_ENDPOINT_URL") or None,
        state_backend=os.environ.get("JOB_STATE_BACKEND", "memory").strip().lower(),
        jobs_table=os.environ.get("JOBS_TABLE_NAME", "bceao-rag-local-jobs"),
        progress_table=os.environ.get("JOB_PROGRESS_TABLE_NAME", "bceao-rag-local-job-progress"),
        dynamodb_endpoint_url=os.environ.get("DYNAMODB_ENDPOINT_URL") or None,
        create_tables=_env_bool("JOB_STATE_CREATE_TABLES", False),
        manifest_backend=os.environ.get("JOB_MANIFEST_BACKEND", "local").strip().lower(),
        # Must match the SQS redrive policy's maxReceiveCount (infra/terraform/modules/
        # queues, docker/elasticmq.conf): on the last attempt a failure is final.
        max_attempts=int(os.environ.get("JOB_MAX_ATTEMPTS", "3")),
        # A queued/running job whose state hasn't been touched for this long is treated
        # as dead (worker OOM-killed, node reclaimed), so it can be re-submitted.
        stale_after_seconds=float(os.environ.get("JOB_STALE_SECONDS", "600")),
        heartbeat_seconds=float(os.environ.get("JOB_HEARTBEAT_SECONDS", "60")),
        # Each heartbeat pushes the in-flight SQS message's visibility this far out.
        visibility_timeout_seconds=int(os.environ.get("JOB_VISIBILITY_TIMEOUT_SECONDS", "900")),
        # After a retryable failure, the message reappears after this many seconds x attempt.
        retry_backoff_seconds=int(os.environ.get("JOB_RETRY_BACKOFF_SECONDS", "60")),
    )
    if settings.queue_backend not in ("inprocess", "sqs"):
        raise JobConfigError(f"JOB_QUEUE_BACKEND must be 'inprocess' or 'sqs', got {settings.queue_backend!r}")
    if settings.state_backend not in ("memory", "dynamodb"):
        raise JobConfigError(f"JOB_STATE_BACKEND must be 'memory' or 'dynamodb', got {settings.state_backend!r}")
    if settings.manifest_backend not in ("local", "s3"):
        raise JobConfigError(f"JOB_MANIFEST_BACKEND must be 'local' or 's3', got {settings.manifest_backend!r}")
    if settings.queue_backend == "sqs":
        if not (settings.crawl_queue_url and settings.ingest_queue_url):
            raise JobConfigError("JOB_QUEUE_BACKEND=sqs needs CRAWL_JOBS_QUEUE_URL and INGEST_JOBS_QUEUE_URL.")
        if settings.state_backend == "memory":
            raise JobConfigError(
                "JOB_QUEUE_BACKEND=sqs needs JOB_STATE_BACKEND=dynamodb: workers run in other "
                "processes, so job status/progress can't live in the API's memory."
            )
    return settings


def get_default_crawl_storage_backend() -> str:
    # Default for CrawlRequest.storage_backend. Set to "s3" on EKS: the pod that crawls
    # and the pod that later ingests are generally not the same, so files must be shared.
    return os.environ.get("CRAWL_STORAGE_BACKEND", "local").strip().lower()
