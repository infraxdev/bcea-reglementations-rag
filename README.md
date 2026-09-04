# BCEAO Regulation Scraper API

A FastAPI service that crawls a starting URL and downloads everything useful for
RAG ingestion: HTML pages (raw HTML + extracted clean text), PDFs, office
documents (doc/docx/xls/xlsx/ppt/pptx/csv/rtf/odt), and video/audio files.

## How it works

- Given a `start_url`, it does a breadth-first crawl restricted to that URL's
  domain (plus any `extra_allowed_domains` you list) **and, by default, to
  that URL's own path subtree** (`restrict_to_start_path`) — starting at
  `/fr/reglementations` won't wander off into unrelated sections reachable
  from the same global nav menu (`/fr/content/...`, `/fr/etats-membres`, ...).
- Any link that looks like a document/video/audio file is downloaded regardless
  of which domain *or path* hosts it (regulations are often served from
  `/sites/default/files/...` or a separate documents subdomain/CDN).
- Paginated listings (`?page=2`, `?paged=3`, etc.) are followed without
  consuming `max_depth` — paging through a listing isn't treated as
  "descending a level" the way following a link to genuinely new content is.
  A same-path link with a *different* filter/category value (e.g. a sidebar
  facet like `?field_hashtags_target_id=166`) is treated as a redundant view
  of content already reachable via the listing's own unfiltered pagination and
  is skipped rather than crawled separately.
- HTML pages get their main content extracted with `trafilatura` (falls back to
  a plain-text dump if extraction fails) and both the raw HTML and the
  extracted `.txt` are saved.
- Downloads are streamed to a temp file, hashed (SHA-256), and deduplicated —
  the same PDF linked from ten different pages is only stored once.
- robots.txt is respected by default, and requests to any single domain are
  throttled (`request_delay_seconds`).
- Storage backend is chosen per-request via `storage_backend: "local" | "s3"`,
  but *where* it points to (local base dir, or bucket/credentials/endpoint) is
  fixed server-side via environment variables — never accepted in the request
  body, so callers can't point the API at an arbitrary bucket or path.
- Crawls run **synchronously** — the request blocks until the crawl finishes
  and returns the full manifest. Use `max_pages`, `max_depth`, and
  `timeout_seconds` to keep requests bounded on large sites.
- Every job's manifest is also saved locally to `job_metadata/<job_id>.json`
  (independent of where the actual files were stored) so you can look it up
  again via `GET /jobs/{job_id}`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure storage (environment variables)

Pick one or configure both — the request just says which one to use for that
crawl via `storage_backend`.

**Local disk:**

| Variable                | Default | Notes                                   |
|--------------------------|---------|------------------------------------------|
| `LOCAL_STORAGE_BASE_DIR` | `data`  | Directory on the API host to write into. |

**S3 / S3-compatible (AWS S3, MinIO, R2, ...):**

| Variable          | Required | Notes                                                        |
|-------------------|----------|----------------------------------------------------------------|
| `S3_BUCKET`       | yes      | Target bucket.                                                 |
| `S3_ENDPOINT_URL` | no       | Set for non-AWS services (e.g. MinIO). Leave unset for AWS S3. |
| `S3_REGION`       | no       | Defaults to `us-east-1`.                                       |
| `S3_ACCESS_KEY`   | no       | Falls back to the server's default AWS credential chain (env vars, `~/.aws/credentials`, IAM role) if unset. |
| `S3_SECRET_KEY`   | no       | Same fallback as above.                                        |
| `S3_PREFIX`       | no       | Key prefix under which every job's files are stored.           |
| `S3_USE_SSL`      | no       | Defaults to `true`.                                             |

```bash
export LOCAL_STORAGE_BASE_DIR=data
# and/or
export S3_BUCKET=bceao-regs
export S3_ENDPOINT_URL=https://minio.example.com
export S3_ACCESS_KEY=...
export S3_SECRET_KEY=...
export S3_PREFIX=raw

uvicorn app.main:app --reload
```

If a crawl requests `storage_backend: "s3"` and `S3_BUCKET` isn't set, the API
returns `400` rather than falling back to local disk.

API docs: http://127.0.0.1:8000/docs

## Example: crawl to local disk

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://www.bceao.int/fr/reglementations",
    "max_depth": 2,
    "max_pages": 100,
    "storage_backend": "local"
  }'
```

## Example: crawl to S3-compatible storage

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://www.bceao.int/fr/reglementations",
    "max_depth": 2,
    "max_pages": 100,
    "storage_backend": "s3"
  }'
```

## Example: only collect PDFs

`resource_types` picks which kinds of resources are actually kept. HTML pages
are always fetched and their links followed (that's how anything else gets
discovered) even when `"html"` is left out of the list — it just won't be
saved itself, only used to find other resources. Non-HTML types not listed
are skipped without downloading their body at all.

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://www.bceao.int/fr/reglementations",
    "max_depth": 2,
    "max_pages": 100,
    "storage_backend": "local",
    "resource_types": ["pdf"]
  }'
```

Valid values: `"html"`, `"pdf"`, `"doc"` (Word/Excel/PowerPoint/CSV/RTF/ODT),
`"video"`, `"audio"`, `"image"`, `"other"` (zip/rar and anything unrecognized).
Default is `["html", "pdf", "doc", "video", "audio"]` — everything except
images and archives, which you can opt into explicitly.

## Example: scrape every regulation across a paginated listing

`https://www.bceao.int/fr/reglementations` lists its documents 12-at-a-time
across ~13 numbered pages (`?page=0` .. `?page=12`), and each list item links
to a detail page whose actual "Télécharger" link points to a PDF under
`/sites/default/files/...`. This is exactly what `restrict_to_start_path`
(default) + depth-free pagination are for:

```bash
curl -X POST http://127.0.0.1:8000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "start_url": "https://www.bceao.int/fr/reglementations",
    "max_depth": 1,
    "max_pages": 2000,
    "storage_backend": "local",
    "resource_types": ["pdf"]
  }'
```

- `max_depth: 1` is enough: page 0 → paginated siblings (depth-free) → detail
  pages under `/fr/reglementations/...` (depth 1) → the PDF each links to
  (resource links ignore depth entirely). Some detail slugs are themselves
  paginated sub-listings (e.g. `/fr/reglementations/reglementation-bancaire`)
  and get their own pagination followed the same way.
- `max_pages` bounds total pages+files processed, not just PDFs — with ~13
  listing pages and a few hundred detail pages in the mix, give it enough
  headroom (a couple thousand) to actually reach the later listing pages
  before the budget runs out.
- Leave `resource_types` at its default (or add `"html"`) if you also want
  the detail pages' text saved, not just the PDFs.

## Response shape

```json
{
  "job_id": "…",
  "status": "completed",
  "stats": {
    "pages_visited": 42,
    "resources_downloaded": 87,
    "resources_duplicate": 5,
    "resources_skipped": 0,
    "resources_failed": 1,
    "bytes_downloaded": 123456789
  },
  "resources": [
    {
      "url": "...",
      "resource_type": "pdf",
      "status": "downloaded",
      "storage_location": "s3://bceao-regs/raw/<job_id>/www.bceao.int/pdf/circulaire-abc123.pdf",
      "sha256": "...",
      "size_bytes": 245678
    }
  ]
}
```

Retrieve a past job's manifest: `GET /jobs/{job_id}`. List known job ids: `GET /jobs`.

## Notes / extension points

- Image and archive links are typed correctly but not auto-followed from page
  links by default (avoids hoovering up every icon/logo) — see
  `AUTO_FOLLOW_TYPES` in `app/utils.py` if you need to change that.
- This service only downloads and lightly extracts text; chunking, embedding,
  and indexing into your vector store are separate downstream steps.
