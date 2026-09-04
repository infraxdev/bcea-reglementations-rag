from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class ResourceType(str, Enum):
    HTML = "html"
    PDF = "pdf"
    DOC = "doc"
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    OTHER = "other"


class ResourceStatus(str, Enum):
    DOWNLOADED = "downloaded"
    DUPLICATE = "duplicate"
    SKIPPED_ROBOTS = "skipped_robots"
    SKIPPED_SIZE = "skipped_size"
    SKIPPED_LIMIT = "skipped_limit"
    SKIPPED_TYPE = "skipped_type"
    FAILED = "failed"


class CrawlRequest(BaseModel):
    start_url: HttpUrl = Field(..., description="Page to start crawling from. Its domain defines the crawl scope.")
    max_depth: int = Field(3, ge=0, le=10, description="How many link-hops of HTML pages to follow from start_url.")
    max_pages: int = Field(
        200, ge=1, le=5000,
        description="Upper bound on total items processed (pages + downloaded files) in this crawl.",
    )
    extra_allowed_domains: list[str] = Field(
        default_factory=list,
        description="Additional domains (besides start_url's own) that are allowed to be crawled as pages, "
        "e.g. a documents subdomain. Resource files (PDFs, docs, videos) are always downloaded "
        "regardless of domain once linked from an allowed page.",
    )
    restrict_to_start_path: bool = Field(
        True,
        description="When true (default), page-links are only followed if their path is start_url's path or "
        "a sub-path of it — e.g. starting at /fr/reglementations won't wander into unrelated site sections "
        "reachable from the same global nav menu (/fr/content/..., /fr/etats-membres, ...). Pagination and "
        "detail pages under the starting section are still followed, and resource files (PDFs, docs, videos) "
        "are never restricted by this since they're often hosted under a completely different path. Set to "
        "false to crawl the whole domain (or extra_allowed_domains) from wherever start_url happens to be.",
    )
    resource_types: list[ResourceType] = Field(
        default_factory=lambda: [
            ResourceType.HTML, ResourceType.PDF, ResourceType.DOC, ResourceType.VIDEO, ResourceType.AUDIO,
        ],
        description="Which resource types to actually download and keep. HTML pages are always fetched and "
        "their links followed for crawling purposes even if 'html' is left out — but if it's left out, page "
        "content itself won't be saved, only used to discover other resources. Non-HTML types not listed here "
        "are skipped without downloading their body. Defaults to everything except images/archives; pass e.g. "
        "[\"pdf\"] to collect only PDFs, or add \"image\"/\"other\" to also pick those up.",
    )
    concurrency: int = Field(5, ge=1, le=20, description="Number of concurrent fetch workers.")
    request_delay_seconds: float = Field(0.5, ge=0, le=10, description="Minimum delay between requests to the same domain.")
    timeout_seconds: float = Field(20, ge=1, le=120, description="Per-request timeout.")
    respect_robots_txt: bool = True
    user_agent: str = "BCEAORegScraper/1.0 (+RAG ingestion bot)"
    max_resource_size_mb: Optional[float] = Field(
        500, ge=1, description="Skip files larger than this. Set to null for no limit."
    )
    storage_backend: Literal["local", "s3"] = Field(
        "local",
        description="Where to persist downloaded files. Both backends are configured server-side via "
        "environment variables (LOCAL_STORAGE_BASE_DIR, or S3_BUCKET/S3_ENDPOINT_URL/S3_REGION/"
        "S3_ACCESS_KEY/S3_SECRET_KEY/S3_PREFIX/S3_USE_SSL) — no credentials or paths are accepted here.",
    )
    job_id: Optional[str] = Field(None, description="Optional custom job id; a UUID is generated if omitted.")


class ResourceRecord(BaseModel):
    url: str
    final_url: str
    depth: int
    resource_type: ResourceType
    content_type: Optional[str] = None
    status: ResourceStatus
    storage_location: Optional[str] = None
    extracted_text_location: Optional[str] = None
    title: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


class CrawlStats(BaseModel):
    pages_visited: int = 0
    resources_downloaded: int = 0
    resources_duplicate: int = 0
    resources_skipped: int = 0
    resources_failed: int = 0
    bytes_downloaded: int = 0


class CrawlResult(BaseModel):
    job_id: str
    start_url: str
    status: Literal["completed", "completed_with_errors"]
    started_at: str
    finished_at: str
    duration_seconds: float
    stats: CrawlStats
    resources: list[ResourceRecord]
