# BCEAO Regulation RAG

A FastAPI service implementing the full pipeline in
`bceao_rag_pipeline_with_guarded_routing.png`: crawl BCEAO regulatory sources,
index them into Qdrant, and answer questions over them with guarded routing
(out-of-scope questions are turned away before any retrieval or answer generation).

## Project structure

Each package below is one swimlane of the diagram.

```
app/
  api/         # FastAPI routers: /crawl+/jobs, /ingest/{job_id}, /query
  crawler/     # Indexing offline · Sources — crawl + download (fully working)
  ingestion/   # Indexing offline · Parse -> VLM normalize -> Chunk -> Embed -> Qdrant
  retrieval/   # Retrieval online · router -> rewrite -> hybrid search -> rerank -> prompt
  generation/  # Generation · LLM -> policy gate -> response
web/           # Next.js tester UI for POST /query (see web/README.md)
docs/          # Architecture decisions — start with docs/aws-architecture.md
infra/         # AWS infrastructure (Terraform + Kubernetes/Argo CD) — see infra/README.md
```

## Deploying to AWS

See [`docs/aws-architecture.md`](docs/aws-architecture.md) for the design and
[`infra/README.md`](infra/README.md) for the bootstrap steps.

Every stage is a small interface (an `ABC` in each package's `interfaces.py`) with
a default implementation:

| Stage | Default | Status |
|---|---|---|
| Sources (crawl) | `crawler.engine.run_crawl` | working |
| Parse | `ingestion.parse.DoclingParser` | working (Docling) |
| VLM normalize | `ingestion.vlm_normalize.NotConfiguredNormalizer` | **TODO** — pick a vision-capable model |
| Chunk | `ingestion.chunk.SimpleChunker` | working (paragraph-aware + overlap) |
| Embed | `ingestion.embed.NotConfiguredEmbedder` | **TODO** — pick a dense/sparse embedding model |
| Qdrant | `ingestion.vector_store.QdrantVectorStore` | working |
| Query router | `retrieval.router.LLMScopeRouter` | working (one LLM call: scope decision + rewritten query, or the reply for small talk / out-of-scope; general finance questions are flagged and answered by the generation LLM with the history, without retrieval) |
| Rewrite query | `retrieval.rewrite.PassthroughRewriter` | working no-op — **TODO** for real metadata extraction |
| Hybrid search | `retrieval.hybrid_search.HybridSearcher` | working once Embed is configured |
| Rerank | `retrieval.rerank.NotConfiguredReranker` | **TODO** — pick a cross-encoder/rerank API |
| Prompt assembly | `retrieval.prompt_assembly.assemble_prompt` | working |
| LLM | `generation.llm.NotConfiguredGenerator` | **TODO** — pick a generation provider |
| Policy gate | `generation.policy_gate.BasicPolicyGate` | working (basic checks; extend for real redaction) |

`POST /ingest/{job_id}` and `POST /query` are wired end-to-end and run until they
hit the first unconfigured stage, where they return `501` with a message
pointing at the file to implement.

## Crawler: how it works

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
- Crawls and ingests run **in the background**: `POST /crawl` and
  `POST /ingest/{job_id}` return `202` with a `job_id` right away (see
  [Jobs: crawl and ingest](#jobs-crawl-and-ingest)).
- Every finished crawl's manifest is saved to `job_metadata/<job_id>.json`
  (or to S3 with `JOB_MANIFEST_BACKEND=s3`), independent of where the files
  themselves went, so you can look it up again via `GET /jobs/{job_id}`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`docling` (the default Parse implementation) pulls in a fair amount of ML tooling, so
this install is noticeably heavier/slower than the crawler-only version was.

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

## Jobs: crawl and ingest

Both are asynchronous. Submit, then poll:

```bash
curl -X POST http://127.0.0.1:8000/crawl -H 'Content-Type: application/json' \
  -d '{"start_url": "https://www.bceao.int/fr/reglementations", "max_depth": 1}'
# -> 202 {"job_id": "3f2a...", "status": "queued", "status_url": "/crawl/3f2a.../status"}

curl http://127.0.0.1:8000/crawl/3f2a.../status     # queued -> running -> completed | failed
curl http://127.0.0.1:8000/jobs/3f2a...             # full manifest, once completed

curl -X POST http://127.0.0.1:8000/ingest/3f2a...   # -> 202, status_url /ingest/3f2a.../progress
curl http://127.0.0.1:8000/ingest/3f2a.../progress  # docs done, rate, ETA, errors
```

Submitting a job id that's still queued or running returns `409`.

Who runs the jobs depends on `JOB_QUEUE_BACKEND`:

| Mode | Set up | Jobs run in | Use for |
|---|---|---|---|
| `inprocess` (default) | `uvicorn` only | the API process | quick local development |
| `sqs` | `docker compose up --build` | separate `worker` containers (`python -m app.worker`) | the local full stack, and EKS |

With `sqs`, failed jobs are retried (3 attempts, then the SQS dead-letter queue), a
worker that stops mid-job hands the job back so another resumes it, and job state is
shared through DynamoDB so any API replica can answer status polls. The settings are
listed in `.env.example` (`JOB_*`), and `docs/aws-architecture.md` §6 describes the
design.

### Full local stack (Docker Compose)

```bash
cp .env.example .env    # then set your provider keys
docker compose up --build
```

| Service | URL | What |
|---|---|---|
| web | http://localhost:8080 | UI (nginx; proxies `/api` to the api) |
| api | http://localhost:8000/docs | FastAPI |
| worker | — | runs crawl/ingest jobs; scale with `docker compose up --scale worker=3` |
| qdrant | http://localhost:6333/dashboard | vector store |
| elasticmq | http://localhost:9325 | local SQS (queues + dead-letter queues) |
| dynamodb | — | local DynamoDB (job status and progress) |

Crawled files and manifests live in the `crawl_data` and `job_metadata` volumes, shared
by the api and worker containers. Ollama is reached on the host at
`host.docker.internal:11434`.

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

## Manifest shape (`GET /jobs/{job_id}`)

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
  `AUTO_FOLLOW_TYPES` in `app/crawler/utils.py` if you need to change that.
- Chunking, embedding, and indexing into Qdrant now live in `app/ingestion/` —
  see the "Project structure" table above for what's implemented vs. a TODO.
- `POST /ingest/{job_id}` indexes both local and S3-backed crawls. For S3 it
  downloads each file to a temp dir to parse it, then moves it to `processed/` in
  the bucket.
# bcea-reglementations-rag
