from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

# extension -> resource type
RESOURCE_EXTENSIONS: dict[str, str] = {
    "pdf": "pdf",
    "doc": "doc", "docx": "doc", "xls": "doc", "xlsx": "doc",
    "ppt": "doc", "pptx": "doc", "odt": "doc", "rtf": "doc", "csv": "doc",
    "mp4": "video", "mov": "video", "avi": "video", "webm": "video", "mkv": "video", "m4v": "video",
    "mp3": "audio", "wav": "audio", "m4a": "audio", "ogg": "audio",
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image", "svg": "image", "webp": "image",
    "zip": "other", "rar": "other",
}

CONTENT_TYPE_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "doc",
    "application/vnd.ms-excel": "doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "doc",
    "application/vnd.ms-powerpoint": "doc",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "doc",
}

# Extensions that are safe to treat as "another HTML page" candidates when crawling links.
PAGE_LIKE_EXTENSIONS = {"", "html", "htm", "php", "asp", "aspx", "jsp"}


def domain_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


# Common pagination query-param names across CMSes (Drupal/Views, WordPress, custom).
_PAGINATION_PARAM_NAMES = {"page", "paged", "p", "pg", "start", "offset"}
# Values that mean "no filter applied" — ignored so a pager link that echoes the exposed
# filters' default/empty values still compares equal to the unfiltered canonical URL.
_NEUTRAL_QUERY_VALUES = {"", "all"}


def _significant_query(url: str) -> frozenset[tuple[str, str]]:
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    return frozenset(
        (k, v) for k, v in pairs
        if k.lower() not in _PAGINATION_PARAM_NAMES and v.strip().lower() not in _NEUTRAL_QUERY_VALUES
    )


def is_same_listing(url_a: str, url_b: str) -> bool:
    """True when two URLs are the same page/path and only differ by pagination (e.g. a
    paginator link like `?page=2`), once empty/neutral filter params are ignored. Used so
    paging through a listing doesn't eat into max_depth the way navigating to genuinely
    different content (a new page, or a different filter/category) does."""
    return (
        domain_of(url_a) == domain_of(url_b)
        and path_of(url_a) == path_of(url_b)
        and _significant_query(url_a) == _significant_query(url_b)
    )


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def resolve_url(base: str, link: str) -> str | None:
    try:
        # Mirror browser URL parsing (WHATWG URL spec): strip ASCII tab/newline/CR
        # wherever they occur, then trim leading/trailing whitespace. Real-world markup
        # sometimes has stray whitespace inside href values (template line-wrapping,
        # truncated auto-generated slugs, etc.) that would otherwise resolve to a
        # subtly different (and 404ing) URL than what a browser actually navigates to.
        cleaned = re.sub(r"[\t\r\n]", "", link).strip()
        resolved = urljoin(base, cleaned)
        if not resolved.lower().startswith(("http://", "https://")):
            return None
        return normalize_url(resolved)
    except Exception:
        return None


_CANONICAL_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="?canonical"?', re.IGNORECASE)


def parse_canonical_link_header(link_header: str) -> str | None:
    """Extract the canonical URL from an HTTP `Link: <url>; rel="canonical"` header, if present.
    Sites sometimes serve the same content at more than one path (e.g. a locale-less URL and a
    locale-prefixed one) and declare which is authoritative this way."""
    if not link_header:
        return None
    match = _CANONICAL_LINK_RE.search(link_header)
    return match.group(1) if match else None


def extension_of(url: str) -> str:
    path = urlsplit(url).path
    return PurePosixPath(path).suffix.lower().lstrip(".")


def classify_resource(url: str, content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in CONTENT_TYPE_MAP:
        return CONTENT_TYPE_MAP[ct]
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("audio/"):
        return "audio"
    if ct.startswith("image/"):
        return "image"
    if ct in ("text/html", "application/xhtml+xml"):
        return "html"

    ext = extension_of(url)
    if ext in RESOURCE_EXTENSIONS:
        return RESOURCE_EXTENSIONS[ext]
    if ext in ("html", "htm", ""):
        return "html"
    return "other"


def probable_resource_type(url: str) -> str | None:
    """Best-guess resource type from the URL's extension alone (no network call).
    Returns None for extensions that look like pages (html/php/no-extension/etc)."""
    return RESOURCE_EXTENSIONS.get(extension_of(url))


def looks_like_resource_link(url: str, requested_types: set[str]) -> bool:
    rtype = probable_resource_type(url)
    return rtype is not None and rtype in requested_types


def looks_like_page_link(url: str) -> bool:
    return extension_of(url) in PAGE_LIKE_EXTENSIONS


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^a-zA-Z0-9\-_.]+", "-", text).strip("-")
    return text[:max_len] or "item"


def storage_key_for(url: str, resource_type: str) -> str:
    parts = urlsplit(url)
    domain = parts.netloc.lower()
    last_segment = PurePosixPath(parts.path).name or "index"
    slug = slugify(last_segment)
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    ext = extension_of(url) or {"html": "html", "pdf": "pdf"}.get(resource_type, "bin")
    return f"{domain}/{resource_type}/{slug}-{url_hash}.{ext}"
