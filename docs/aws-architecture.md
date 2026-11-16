# AWS Infrastructure Plan — BCEAO Regulation RAG

Status: proposal · Owner: TBD · Last updated: 2026-11-06

## 0. Grounding: what the code already tells us

Before picking AWS services, these facts from the current implementation shape every
decision below:

| Fact | Where | Infra implication |
|---|---|---|
| `/query` is stateless — client resends `history`/`history_summary` each call | `app/api/query.py` | API tier scales horizontally with zero session affinity / sticky routing needed |
| `/crawl` ran **synchronously** in the request (now queued, §6) | `app/api/crawl.py` | Needs either a long request timeout end-to-end or decoupling to a queue (see §4) |
| `/ingest/{job_id}` ran as an **in-process `asyncio.create_task`**, progress in an **in-memory dict** (now queued, §6) | `app/api/ingest.py`, `app/ingestion/progress.py` | Breaks across pod restarts and multi-replica deployments today — must be externalized to run more than one API replica safely |
| Ingest is explicitly **safe to re-run** — already-processed files are skipped | `app/api/ingest.py` docstring | Makes Spot interruption and at-least-once queue delivery low-risk once decoupled |
| Job manifests are written to **local disk** (`job_metadata/*.json`) | `app/crawler/job_store.py` | Needs to move to S3/DynamoDB for multi-replica/multi-AZ |
| Storage backend is already pluggable `local` \| `s3`, chosen server-side via env vars | `app/config.py`, `app/crawler/storage/` | No app change needed — just set `S3_BUCKET` etc. in prod; S3 creds should come from the IAM role, not static keys (code already falls back to boto3's default credential chain) |
| Embedding (`multilingual-e5-large` + BM25) and reranking (`jina-reranker-v2-base-multilingual`) run **locally via fastembed/ONNX on CPU** — no GPU needed | `app/ingestion/embed.py`, `app/retrieval/rerank.py` | CPU-optimized nodes suffice; multi-GB model weights should be baked into the image, not re-downloaded per pod |
| Docling parsing + RapidOCR is the heaviest CPU/memory step | `app/ingestion/parse.py`, `requirements.txt` | Deserves its own worker node pool, separate from the API tier |
| Generation supports `ollama` (self-hosted) \| `openai` \| `anthropic`, selectable per-request | `app/generation/llm.py`, `.env.example` | Keep all three; default prod to a hosted API, keep Ollama path alive for sovereignty/offline need |
| Code **already anticipates EKS** ("override `OLLAMA_BASE_URL` to point at an in-cluster Ollama Service... when deployed to EKS") | `app/config.py:79`, `app/generation/llm.py:34` | EKS is the target orchestrator, not a fresh choice made for this doc |
| Documents are **French** (multilingual-e5, BM25 French stopwords), institution is UEMOA/West Africa | `app/ingestion/embed.py` | Region choice should weigh proximity to West Africa + French-language ops (see §1) |
| Frontend (`web/`) is a thin client — the only backend call is a client-side `fetch` in `lib/api.ts`, no server-side data fetching found | `web/lib/api.ts` | Exportable as a fully static site, served by nginx on the cluster (§5) |

**Assumption flagged for confirmation:** region. BCEAO serves 8 West African countries;
AWS has no region on that coastline. I'm defaulting to **eu-west-3 (Paris)** — full
service parity, lowest cost of the realistic options, good historical network paths
from West Africa to Europe, and francophone ops alignment — over **af-south-1 (Cape
Town)**, which is in-continent but ~4,800km from Dakar/Abidjan with a narrower service
catalog and ~15-20% higher prices. If in-continent data residency is a hard compliance
requirement, swap to af-south-1; nothing else in this plan changes.

## 1. Account & network foundation

- **AWS Organizations**, 3 accounts minimum: `prod`, `staging`/`dev`, `log-archive`
  (CloudTrail org trail + centralized log sink). Keeps prod blast radius isolated and
  billing/IAM boundaries clean — worth the setup cost given the regulatory-adjacent
  context even though the regulations themselves are public documents.
- One VPC per environment, 3 AZs in prod (2 in dev/staging to cut NAT cost), e.g.
  `10.0.0.0/16`:
  - Public subnets: ALB, NAT Gateways only.
  - Private subnets: EKS nodes, Qdrant, Ollama.
  - No subnet needs to be fully isolated (no egress) — everything already talks to S3/ECR/Secrets Manager via VPC endpoints (below), and nothing holds secrets that must never reach the internet path.
- **VPC Endpoints** (Gateway: S3; Interface: ECR API/DKR, STS, Secrets Manager,
  CloudWatch Logs, SQS, DynamoDB) — avoids routing S3/ECR pulls and Secrets Manager
  reads through NAT, which is both cheaper and keeps that traffic off the public
  internet entirely.
- NAT Gateway per AZ in prod for HA; single NAT in dev/staging.

## 2. Compute: EKS

**Why EKS over ECS Fargate:** the code's own comments already target an in-cluster
Ollama Service reachable via `OLLAMA_BASE_URL`; Karpenter + KEDA give the
bursty crawl/ingest workload Spot-friendly, scale-to-zero autoscaling that Fargate
can't match as cleanly; and a future GPU node pool for self-hosted Ollama is a one-line
Karpenter NodePool, not a new compute platform. ECS Fargate remains the lower-ops
fallback if the team wants to avoid Kubernetes entirely — flagging that as a legitimate
alternative, not a wrong choice, but EKS is the recommendation here.

- EKS control plane, one cluster per environment, version pinned and upgraded on a
  quarterly cadence.
- Add-ons: AWS Load Balancer Controller, **Karpenter** (node autoscaling), **KEDA**
  (queue-depth-based pod autoscaling for workers), EBS CSI driver, External Secrets
  Operator, cert-manager, metrics-server, plus the observability stack
  (`kube-prometheus-stack`, Loki, Tempo — see §7).
- Node pools (Karpenter `NodePool`s, each tainted so only its workload schedules there):

  | Pool | Workload | Instance shape | Capacity type | Scaling |
  |---|---|---|---|---|
  | `system` | cluster add-ons | small general-purpose (e.g. `m7g.medium`) | On-Demand | fixed small floor |
  | `api` | FastAPI `Deployment` (stateless) | general purpose (e.g. `m7i.large`) | On-Demand | HPA on CPU + p95 latency, min 2 replicas across AZs |
  | `ingest-worker` | crawl + ingest jobs (Docling/OCR/embedding — CPU+memory heavy) | compute/memory optimized (e.g. `c7i.xlarge`) | **Spot** (jobs are resumable — safe) | KEDA on SQS queue depth, scale to zero |
  | `qdrant` | Qdrant `StatefulSet` | memory optimized (e.g. `r7i.large`) | On-Demand (stateful) | fixed, EBS gp3 PVC via EBS CSI |
  | `llm-gpu` *(optional, Phase 3)* | self-hosted Ollama | `g5.xlarge` (A10G) | On-Demand, scale-to-zero via Karpenter | only provisioned when the sovereignty/offline use case is actually needed |

- **Ingress**: AWS Load Balancer Controller provisions an ALB from a k8s `Ingress`;
  TLS terminates at the ALB via an ACM cert; a **WAFv2 Web ACL** (AWS managed rule
  groups + a rate-based rule) is attached directly to the ALB. This is the only
  public-facing compute surface besides the frontend.
- Skip a service mesh for now — nothing here needs mTLS between more than a
  handful of in-cluster services; revisit only if that changes.

## 3. Storage

- **S3**, one bucket per environment (versioned, SSE-KMS):
  - `bceao-rag-<env>` with prefixes `raw/` and `processed/` (matches the crawler's
    existing `S3_PREFIX` support — no app change) for crawled documents.
  - `bceao-rag-qdrant-snapshots-<env>` for nightly Qdrant backups.
  - Lifecycle: `raw/` objects older than 90 days → Glacier Instant Retrieval (regs
    rarely need re-parsing once ingested); `processed/` and manifests stay Standard.
- **DynamoDB** (on-demand billing), introduced in Phase 2 (§6):
  - `jobs` — replaces local `job_metadata/*.json`, PK `job_id`.
  - `job_progress` — replaces the in-memory dict in `ingestion/progress.py`, PK `job_id`.
- **EBS gp3** for Qdrant's PVC (start 100GB, monitor growth), daily AWS Backup snapshot.
- **ECR** for the app image(s) — one image, two entrypoints (`uvicorn app.main:app` for
  the API Deployment, a small `app/worker.py` long-poll loop for the worker Deployment
  (§6).
- Deliberately **no EFS**: bake the multi-GB fastembed/rerank model weights
  (`multilingual-e5-large`, BM25, `jina-reranker-v2-base-multilingual`) into the
  container image at build time instead of mounting a shared cache volume — simpler,
  no cross-pod cache-coherency concerns, and new pods are ready to serve immediately
  instead of re-downloading from HuggingFace on cold start. Docling's layout/table
  models and RapidOCR's OCR models are baked in the same way (`docker/warm_models.py`
  runs a real parse at build time), and the image sets `HF_HUB_OFFLINE=1`, so worker
  pods that KEDA starts from zero never download anything before their first ingest.
- **CPU-only PyTorch** in the image (Docling needs torch, but no node pool running this
  image has a GPU). The default CUDA wheel would add ~4–5 GB of unused libraries.
  GPU-accelerated ingestion would be a separate image and node pool, worth it only if
  per-document model time turns out to dominate (measure first).

## 4. Secrets & configuration

- **AWS Secrets Manager** for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `QDRANT_API_KEY`
  — synced into the cluster as native k8s `Secret`s via the External Secrets Operator,
  mounted as the exact same env vars `app/config.py` already reads. Zero app code change.
- Non-secret config (`QDRANT_URL`, `GENERATION_PROVIDER`, `CORS_ALLOWED_ORIGINS`, model
  names) as a per-environment `ConfigMap`.
- **IRSA** (IAM Roles for Service Accounts): API and worker pods assume a scoped IAM
  role for S3/DynamoDB/SQS access. Leave `S3_ACCESS_KEY`/`S3_SECRET_KEY` **unset** —
  boto3's default credential chain picks up the IRSA role automatically, which
  `app/config.py`'s own fallback comment already anticipates. No static AWS keys
  anywhere in the system.

## 5. Frontend (`web/`)

`web/lib/api.ts` only does a client-side `fetch` against the backend; no server-side
data fetching was found in `app/`/`lib/`. So the app is built as a **static export**
(`output: "export"` in `web/next.config.ts`) and **served from the EKS cluster**:

- **Image**: `web/Dockerfile` runs `next build` and serves `out/` with
  `nginx-unprivileged` (non-root, port 8080, ~50 MB). Pushed to its own ECR repo,
  **`bceao-rag-web`**, tagged by git SHA (`.github/workflows/cd-web.yaml`). It's a
  separate build and release cadence from the Python image.
- **Same-origin API**: the frontend is built with `NEXT_PUBLIC_API_BASE_URL=/api`, and
  nginx proxies `/api/*` to the `api` Service (`API_UPSTREAM`, default `http://api`).
  The browser only talks to one origin, so **no CORS is needed for the web UI**, and no
  environment-specific hostname is baked into the image. The same image is promoted
  dev → staging → prod.
- **K8s**: `infra/kubernetes/apps/web` (Deployment + Service + PDB, on the `api` node
  pool), exposed through a second host rule on the existing Ingress. It joins the
  `bceao-rag` ALB group, so it **shares the ALB, ACM certificate and WAF** already in
  place: no extra load balancer or Web ACL. The cert must cover both hosts.
- **Why not S3 + CloudFront** (the original recommendation): at this traffic level
  both cost about the same (CloudFront's free tier covers it). The real extra cost would
  have been a second WAF Web ACL on CloudFront (~$10–15/mo). The in-cluster option also
  keeps a single deploy path (image → ECR → Argo CD) and avoids CORS. CloudFront would
  give edge caching and keep the UI up during a cluster outage, but the UI is unusable
  without the API anyway. Revisit if traffic grows a lot or users far from eu-west-3
  report slow loads.
- **If SSR/ISR is ever needed**: drop `output: "export"` and run `next start` in the
  same Deployment instead of nginx.

## 6. Decoupling crawl & ingest (implemented)

The api and the worker are separate Deployments of the same image. The api only
accepts jobs; worker pods run them. Code: `app/jobs/` (dispatch, state, runner) and
`app/worker.py` (SQS consumer).

- **Submit**: `POST /crawl` and `POST /ingest/{job_id}` record the job as `queued`,
  send a message to the `crawl-jobs` / `ingest-jobs` SQS queue and return **202** with
  the job id. Re-submitting a job that's still queued/running returns 409.
- **Run**: `python -m app.worker` long-polls both queues (one job at a time per queue
  per pod) and calls the existing `run_crawl` / `index_crawl_job`. While a job runs, a
  heartbeat every 60 s extends the message's visibility and touches the job's state.
- **Outcomes**: success, permanent error (bad request, missing manifest,
  misconfiguration) or duplicate → message deleted. Other errors → retried with backoff;
  after `JOB_MAX_ATTEMPTS` (3, = the queue's `maxReceiveCount`) the job is marked
  `failed` and SQS moves the message to the DLQ.
- **Shutdown** (deploy, scale-in, Spot reclaim): SIGTERM → the worker cancels the job
  and releases its message at once; another pod resumes it. Retries are safe by
  construction: ingest skips files already moved to `processed/`.
- **State**, readable from any api replica:
  - crawl status → DynamoDB `jobs` table (`GET /crawl/{job_id}/status`);
  - ingest progress → DynamoDB `job_progress` table (`GET /ingest/{job_id}/progress`);
  - crawl manifests → S3 `job_metadata/<job_id>.json` (`GET /jobs/{job_id}`), since a
    big crawl's manifest can exceed DynamoDB's 400 KB item limit;
  - crawled files → S3 (`CRAWL_STORAGE_BACKEND=s3`). Ingestion downloads each file to
    a temp dir to parse it, then moves it to `processed/` in S3.
  A job whose state hasn't been touched for `JOB_STALE_SECONDS` (10 min) is treated as
  dead and can be re-submitted.
- **Scaling**: KEDA scales the worker on both queues' depth, down to zero between runs;
  Karpenter then removes the `ingest-worker` nodes.
- **Local**: `compose.yml` runs the same code against ElasticMQ (SQS) and DynamoDB
  Local, with shared volumes in place of S3. Plain `uvicorn` with the defaults
  (`JOB_QUEUE_BACKEND=inprocess`, `JOB_STATE_BACKEND=memory`) still runs jobs inside
  the API process, with no extra services.

## 7. Observability

Self-hosted on the cluster instead of AMP/AMG — kube-prometheus-stack (Prometheus +
Grafana) + Loki + Tempo, all via Helm. Trades a recurring managed-service fee for
compute/storage cost plus some ops burden, which at this scale is the right trade, and
keeps the whole stack portable (no AWS-specific metrics/logs/traces APIs).

**Why not AMP/AMG:** they aren't a full substitute anyway — AMP covers metrics only
and AMG is just a managed Grafana frontend; neither has a managed Loki/Tempo
equivalent (AWS's nearest analogues, CloudWatch Logs and X-Ray, speak different
APIs). Since Loki+Tempo are self-hosted regardless, and Prometheus+Grafana are the
easiest part of that same Helm-based stack to also run, mixing in AMP/AMG would only
split dashboards/alerts/auth across two systems for a modest ops saving — worth
revisiting only if this grows into a multi-cluster fleet needing metric federation.

- **Metrics**: `kube-prometheus-stack` (Prometheus + Alertmanager + Grafana).
  Dashboards for crawl pages/sec, ingest docs/sec (from `IngestProgress`), `/query`
  latency p50/p95, per-provider LLM error rate, Qdrant query latency. A small
  `yet-another-cloudwatch-exporter` (or the AWS CloudWatch exporter) pulls the AWS-side
  metrics Prometheus can't scrape directly (ALB 5xx rate, NAT bytes, EBS/SQS metrics)
  into the same Prometheus, so Grafana stays the single pane of glass rather than
  splitting dashboards across CloudWatch and Grafana.
- **Logs**: Promtail DaemonSet → **Loki**, queried from Grafana (Explore + log-based
  dashboards). ALB access logs and VPC flow logs still land in S3/CloudWatch directly
  (that's where AWS writes them) but app/pod logs go to Loki, not CloudWatch Logs.
- **Traces**: OpenTelemetry SDK in the FastAPI app → **Tempo**, to see the full
  crawl→ingest→retrieve→generate chain for a single request in Grafana — useful for
  debugging why a particular query returned weak sources. Grafana's trace-to-logs/
  trace-to-metrics linking ties a slow `/query` straight to its Loki logs and
  Prometheus metrics for that time window.
- **Storage backend for Loki/Tempo**: S3 (not local disk/EBS) — the standard
  production setup for both, cheap at this retention, durable, and avoids sizing EBS
  volumes for log/trace growth. Same IRSA pattern as everywhere else: Loki/Tempo pods
  assume a scoped role for their own `bceao-rag-loki-<env>` / `bceao-rag-tempo-<env>`
  buckets. Prometheus itself still needs a PVC (gp3) for its local TSDB — retention
  tuned to what fits comfortably (e.g. 15 days hot, nothing older needed given Grafana
  isn't the system of record for anything compliance-relevant).
- **Alerting**: Grafana unified alerting → Slack/PagerDuty directly for anything
  Prometheus scrapes (DLQ depth > 0, Qdrant pod restarts, ALB 5xx rate, ingest failure
  rate, LLM provider error rate) — no SNS hop needed there. SNS/EventBridge stays only
  for AWS-native signals that aren't metrics (GuardDuty findings, Config rule drift).
- Where this stack runs: a small dedicated `observability` node pool (Prometheus and
  Loki ingestion can get memory-hungry) is cleaner than squeezing it onto `system`, but
  for an MVP-sized cluster it's fine to start on `system` with explicit resource
  requests/limits and split out later if metric/log cardinality grows.
- Synthetic check: a scheduled canary (even a simple CronJob) hitting `/health` and a
  real `/query`, scraped by Prometheus like everything else.

## 8. Security & compliance posture

- WAF on the ALB (covers both the api and web hosts).
- Security groups scoped per tier (API SG → Qdrant SG on 6333/6334 only; workers have
  no inbound rule at all).
- Encryption everywhere: EBS (KMS), S3 (SSE-KMS), Secrets Manager (KMS), TLS on the ALB.
- CloudTrail org trail → `log-archive` account, AWS Config, GuardDuty enabled in prod.
- SCPs at the Organizations level pinning the allowed region(s) and blocking
  high-risk actions (e.g. disabling CloudTrail) in the prod account.
- The regulations themselves are public documents, but query logs reveal *what
  regulated institutions are asking about* — worth protecting with the same rigor as
  the rest, even though the corpus itself isn't confidential.

## 9. Backup / DR

- Qdrant: nightly snapshot → S3, optionally cross-region replicated. RPO ~24h is fine
  given ingestion is batch, not continuous. Documented restore runbook.
- DynamoDB: point-in-time recovery enabled.
- S3: versioning on; cross-region replication optional for `raw/`/`processed/`.
- Multi-AZ by default in prod; multi-region is very likely overkill for this
  workload — revisit only if an explicit uptime SLA demands it.

## 10. CI/CD & IaC

- **Terraform**, one state per environment, remote state in S3 + a DynamoDB lock
  table. Modules: `vpc`, `eks`, `karpenter`, `s3`, `dynamodb`, `sqs`, `iam` (IRSA
  roles), `secrets`.
- GitHub Actions: PR → lint/test (pytest, eslint) + build + Trivy scan; merge to
  `main` → push to ECR (tag = git SHA) → GitOps sync. Recommend **Argo CD** reading a
  separate `-deploy` repo for auditability of what's running in prod at any time —
  valuable given the institutional context.
- Manual approval gate before prod promotion.

## 11. Rough cost shape (prod, steady state, eu-west-3, excluding LLM API usage)

| Line item | Est. monthly |
|---|---|
| EKS control plane | $73 (flat) |
| `api` pool, 2× m7i.large on-demand | ~$140 |
| `qdrant` pool, 1× r7i.large on-demand + EBS gp3 100GB | ~$160 |
| NAT Gateways (3 AZ) + data processing | ~$100–150 |
| ALB + WAF | ~$30–50 |
| `ingest-worker` pool (Spot, scale-to-zero, intermittent) | ~$50–150 (crawl-cadence dependent) |
| Observability (Prometheus/Loki/Tempo/Grafana): node capacity + Prometheus EBS gp3 + Loki/Tempo S3 | ~$60–110 |
| S3 (app buckets) / DynamoDB / SQS / CloudWatch (AWS-native logs only) | ~$20–40 at this scale |
| **Subtotal (no self-hosted LLM)** | **~$615–870/mo** |
| `llm-gpu` pool, if always-on g5.xlarge | **+~$730/mo** — strongly recommend scale-to-zero via Karpenter if this path is used at all |

LLM API costs (OpenAI/Anthropic) are usage-based and billed separately from AWS;
budget them against expected query volume once the feature is live.

## 12. Phased rollout

1. **Phase 0 — foundation.** Terraform VPC + EKS + ECR + S3 + IRSA. Ship the app
   *as-is* (single API Deployment, crawl/ingest still in-process/synchronous, as today)
   behind ALB + WAF. Qdrant as a single pod + EBS. Set `storage_backend=s3`. The web UI
   is served same-origin through its nginx `/api` proxy (§5), so `CORS_ALLOWED_ORIGINS`
   only matters for other browser clients calling the API host directly. This alone is a secure,
   production-reachable deployment with **zero app changes**.
2. **Phase 1 — decouple jobs** (§6). SQS + DynamoDB + dedicated worker Deployment +
   KEDA. **App side done** (`app/jobs/`, `app/worker.py`); the api/worker ConfigMaps
   already set `JOB_QUEUE_BACKEND=sqs`, so Phases 0 and 1 can ship together. Crawl/ingest
   now scale independently and survive pod restarts and Spot interruption.
3. **Phase 2 — observability & hardening** (§7–9). Prometheus/Loki/Tempo/Grafana, OTel tracing,
   CloudTrail/Config/GuardDuty, backup/DR runbooks, Argo CD GitOps.
4. **Phase 3 — optional.** GPU `llm-gpu` node pool for self-hosted Ollama (sovereignty/
   offline need), multi-region DR if an SLA demands it, wiring in a VLM normalizer
   (e.g. DeepSeek-OCR via Ollama, per the TODO in `app/ingestion/vlm_normalize.py`) —
   infra-wise this is just adding the already-designed GPU node pool, no other
   architectural change.
