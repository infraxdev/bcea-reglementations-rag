from __future__ import annotations

import asyncio
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from .extractor import extract_html, extract_links
from .models import (
    CrawlRequest,
    CrawlResult,
    CrawlStats,
    ResourceRecord,
    ResourceStatus,
    ResourceType,
)
from .robots import RobotsCache
from .storage import build_storage
from .utils import (
    classify_resource,
    domain_of,
    is_same_listing,
    looks_like_page_link,
    looks_like_resource_link,
    normalize_url,
    parse_canonical_link_header,
    path_of,
    resolve_url,
    sha256_of_file,
    storage_key_for,
)


class _DomainThrottle:
    """Keeps requests to any single domain at least `delay` seconds apart."""

    def __init__(self, delay: float):
        self.delay = delay
        self._last: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, domain: str) -> None:
        if self.delay <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            last = self._last.get(domain, 0.0)
            sleep_for = self.delay - (now - last)
            self._last[domain] = (last + self.delay) if sleep_for > 0 else now
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)


async def _resolve_canonical(client: httpx.AsyncClient, url: str) -> str | None:
    """Some sites serve the same content at more than one path (e.g. a locale-less URL
    and a locale-prefixed one) and declare the authoritative one via a canonical Link
    header. A cheap HEAD probe lets the crawl start from there so path-based scoping
    lines up with the site's own internal links instead of silently excluding them."""
    try:
        resp = await client.head(url, timeout=10)
    except Exception:
        return None
    canonical = parse_canonical_link_header(resp.headers.get("link", ""))
    if not canonical:
        return None
    return resolve_url(str(resp.url), canonical)


async def run_crawl(req: CrawlRequest) -> CrawlResult:
    job_id = req.job_id or uuid4().hex
    started_at = datetime.now(timezone.utc)
    start_time = time.monotonic()

    storage = build_storage(req.storage_backend, job_id)
    max_bytes = int(req.max_resource_size_mb * 1024 * 1024) if req.max_resource_size_mb else None
    requested_types = {t.value for t in req.resource_types}

    stats = CrawlStats()
    resources: list[ResourceRecord] = []
    content_hashes: dict[str, str] = {}
    state_lock = asyncio.Lock()
    throttle = _DomainThrottle(req.request_delay_seconds)

    start_url_norm = normalize_url(str(req.start_url))
    start_domain = domain_of(start_url_norm)

    async with httpx.AsyncClient(
        timeout=req.timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": req.user_agent},
    ) as client:
        canonical = await _resolve_canonical(client, start_url_norm)
        if canonical and domain_of(canonical) == start_domain:
            start_url_norm = canonical

        allowed_domains = {start_domain} | {d.lower() for d in req.extra_allowed_domains}
        start_path = path_of(start_url_norm)
        start_path_prefix = start_path.rstrip("/") + "/"

        seen_urls: set[str] = {start_url_norm}
        queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        await queue.put((start_url_norm, 0))

        def in_start_scope(url: str) -> bool:
            if not req.restrict_to_start_path or domain_of(url) != start_domain:
                return True
            p = path_of(url)
            return p == start_path or p.startswith(start_path_prefix)

        robots_cache = RobotsCache(req.user_agent, client) if req.respect_robots_txt else None

        async def enqueue(url: str, depth: int) -> None:
            norm = normalize_url(url)
            async with state_lock:
                if norm in seen_urls:
                    return
                seen_urls.add(norm)
            await queue.put((norm, depth))

        async def record(rec: ResourceRecord) -> None:
            async with state_lock:
                resources.append(rec)
                if rec.status == ResourceStatus.DOWNLOADED:
                    if rec.resource_type == ResourceType.HTML:
                        stats.pages_visited += 1
                    stats.resources_downloaded += 1
                    stats.bytes_downloaded += rec.size_bytes or 0
                elif rec.status == ResourceStatus.DUPLICATE:
                    stats.resources_duplicate += 1
                elif rec.status == ResourceStatus.FAILED:
                    stats.resources_failed += 1
                else:
                    stats.resources_skipped += 1

        async def budget_available() -> bool:
            async with state_lock:
                return len(resources) < req.max_pages

        async def handle_html_links(html_path: Path, page_url: str, depth: int) -> None:
            follow_child_pages = depth < req.max_depth
            try:
                html_text = html_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return
            for raw_link in extract_links(html_text, page_url):
                resolved = resolve_url(page_url, raw_link)
                if not resolved:
                    continue

                if looks_like_resource_link(resolved, requested_types):
                    await enqueue(resolved, depth + 1)
                    continue

                if (
                    domain_of(resolved) not in allowed_domains
                    or not looks_like_page_link(resolved)
                    or not in_start_scope(resolved)
                ):
                    continue

                if path_of(resolved) == path_of(page_url):
                    if is_same_listing(resolved, page_url):
                        # Paginator link on the same listing view (e.g. ?page=2) — keep
                        # paging through it at the same depth so a paginated index isn't
                        # capped by max_depth the way real navigation to new content is.
                        await enqueue(resolved, depth)
                    # Same path but a different filter/facet combination (e.g. a category
                    # sidebar link) — skip it. It's a redundant subset of content already
                    # reachable via this listing's own unfiltered pagination, and following
                    # every facet combination would blow up the crawl for no new documents.
                elif follow_child_pages:
                    await enqueue(resolved, depth + 1)

        async def process(url: str, depth: int) -> None:
            if not await budget_available():
                await record(ResourceRecord(
                    url=url, final_url=url, depth=depth, resource_type=ResourceType.OTHER,
                    status=ResourceStatus.SKIPPED_LIMIT, error="max_pages reached",
                ))
                return

            if robots_cache and not await robots_cache.can_fetch(url):
                await record(ResourceRecord(
                    url=url, final_url=url, depth=depth, resource_type=ResourceType.OTHER,
                    status=ResourceStatus.SKIPPED_ROBOTS, error="disallowed by robots.txt",
                ))
                return

            await throttle.wait(domain_of(url))

            tmp_path: Path | None = None
            try:
                async with client.stream("GET", url) as resp:
                    final_url = str(resp.url)
                    content_type = resp.headers.get("content-type", "").split(";")[0].strip()
                    rtype = classify_resource(final_url, content_type)

                    if resp.status_code >= 400:
                        await record(ResourceRecord(
                            url=url, final_url=final_url, depth=depth,
                            resource_type=ResourceType(rtype), content_type=content_type,
                            status=ResourceStatus.FAILED, error=f"HTTP {resp.status_code}",
                        ))
                        return

                    # HTML is always fetched (needed to discover further links) even if not
                    # itself requested; any other type not in resource_types is skipped here
                    # without downloading its body.
                    if rtype != "html" and rtype not in requested_types:
                        await record(ResourceRecord(
                            url=url, final_url=final_url, depth=depth,
                            resource_type=ResourceType(rtype), content_type=content_type,
                            status=ResourceStatus.SKIPPED_TYPE,
                            error=f"resource_type '{rtype}' not in requested resource_types",
                        ))
                        return

                    fd, tmp_name = tempfile.mkstemp(prefix="crawl_")
                    tmp_path = Path(tmp_name)
                    size = 0
                    truncated = False
                    with open(fd, "wb") as f:
                        async for chunk in resp.aiter_bytes(1 << 16):
                            size += len(chunk)
                            if max_bytes and size > max_bytes:
                                truncated = True
                                break
                            f.write(chunk)

                    if truncated:
                        await record(ResourceRecord(
                            url=url, final_url=final_url, depth=depth,
                            resource_type=ResourceType(rtype), content_type=content_type,
                            status=ResourceStatus.SKIPPED_SIZE,
                            error=f"exceeds max_resource_size_mb={req.max_resource_size_mb}",
                        ))
                        return

                digest = await asyncio.to_thread(sha256_of_file, tmp_path)

                if rtype == "html":
                    # Always follow links from an HTML page, whether or not the page
                    # itself is being kept, and regardless of duplicate content.
                    await handle_html_links(tmp_path, final_url, depth)
                    if "html" not in requested_types:
                        await record(ResourceRecord(
                            url=url, final_url=final_url, depth=depth, resource_type=ResourceType.HTML,
                            content_type=content_type, status=ResourceStatus.SKIPPED_TYPE,
                            sha256=digest, size_bytes=size,
                            error="resource_type 'html' not in requested resource_types (links were still followed)",
                        ))
                        return

                async with state_lock:
                    existing_location = content_hashes.get(digest)

                if existing_location:
                    await record(ResourceRecord(
                        url=url, final_url=final_url, depth=depth, resource_type=ResourceType(rtype),
                        content_type=content_type, status=ResourceStatus.DUPLICATE,
                        storage_location=existing_location, sha256=digest, size_bytes=size,
                    ))
                    return

                key = storage_key_for(final_url, rtype)
                location = await storage.save_file(key, tmp_path, content_type)
                async with state_lock:
                    content_hashes[digest] = location

                title = None
                extracted_text_location = None
                if rtype == "html":
                    html_text = tmp_path.read_text(encoding="utf-8", errors="ignore")
                    title, text = extract_html(html_text, final_url)
                    if text:
                        text_key = key.rsplit(".", 1)[0] + ".txt"
                        extracted_text_location = await storage.save_bytes(
                            text_key, text.encode("utf-8"), "text/plain; charset=utf-8"
                        )

                await record(ResourceRecord(
                    url=url, final_url=final_url, depth=depth, resource_type=ResourceType(rtype),
                    content_type=content_type, status=ResourceStatus.DOWNLOADED,
                    storage_location=location, extracted_text_location=extracted_text_location,
                    title=title, sha256=digest, size_bytes=size,
                ))
            except Exception as exc:
                # httpx's timeout/connection exceptions frequently stringify to "" —
                # fall back to the exception's class name so failures stay diagnosable.
                message = str(exc) or type(exc).__name__
                await record(ResourceRecord(
                    url=url, final_url=url, depth=depth, resource_type=ResourceType.OTHER,
                    status=ResourceStatus.FAILED, error=message,
                ))
            finally:
                if tmp_path and tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

        async def worker() -> None:
            while True:
                url, depth = await queue.get()
                try:
                    await process(url, depth)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(req.concurrency)]
        await queue.join()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    finished_at = datetime.now(timezone.utc)
    status = "completed" if stats.resources_failed == 0 else "completed_with_errors"
    return CrawlResult(
        job_id=job_id,
        start_url=str(req.start_url),
        status=status,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=round(time.monotonic() - start_time, 2),
        stats=stats,
        resources=resources,
    )
