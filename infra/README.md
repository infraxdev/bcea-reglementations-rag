# Infrastructure

Implements `docs/aws-architecture.md`. Read that first — this is the "how", that's the
"why". Three layers, applied in order:

```
infra/
├── terraform/        # AWS account-level resources: VPC, EKS, IAM/IRSA, S3, DynamoDB,
│                      # SQS, Secrets Manager, ECR, WAF — one state per environment
├── kubernetes/        # Everything that runs inside the cluster: add-ons (Helm) +
│                      # this app's own Deployments/StatefulSets (Kustomize), wired
│                      # together via Argo CD (GitOps — this repo is the source of truth)
└── scripts/           # One-off operator helpers that don't belong in CI
```

## Bootstrap order (first time, per AWS account)

1. **Terraform remote state backend** — `infra/terraform/bootstrap/` creates the S3
   bucket + DynamoDB lock table every environment's `backend.tf` points at. Applied
   once, locally, with local state (nothing else to point it at yet):
   ```bash
   cd infra/terraform/bootstrap
   terraform init
   terraform apply -var="account_name=nonprod"   # or "prod" in the prod account
   ```
2. **Environment infra** — `infra/terraform/environments/<env>/`:
   ```bash
   cd infra/terraform/environments/dev
   terraform init
   terraform plan
   terraform apply
   ```
   Note every output — the `kubernetes/` layer below is full of
   `REPLACE_WITH_TERRAFORM_OUTPUT_*` placeholders that these outputs fill in.
3. **Populate the real secret values** — `infra/terraform/modules/secrets` only
   creates the Secrets Manager *containers* (deliberately — see that module's
   comment). Set the real `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`QDRANT_API_KEY` values
   out of band:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id bceao-rag/dev/OPENAI_API_KEY --secret-string "sk-..."
   ```
4. **Point `kubectl` at the new cluster**:
   ```bash
   aws eks update-kubeconfig --name bceao-rag-dev --region eu-west-3
   ```
5. **Namespaces** (owned here, not by any individual Helm/Kustomize app — see that
   file's header comment):
   ```bash
   kubectl apply -f infra/kubernetes/namespaces.yaml
   ```
6. **Argo CD itself**, then the app-of-apps that takes over from here:
   ```bash
   helm install argocd argo/argo-cd -n argocd -f infra/kubernetes/addons/argocd/values.yaml
   # Before this step: fill in every REPLACE_WITH_TERRAFORM_OUTPUT_* and
   # REPLACE_WITH_GIT_REPO_URL placeholder across infra/kubernetes/ — grep for them:
   grep -rl "REPLACE_WITH_" infra/kubernetes/
   kubectl apply -f infra/kubernetes/argocd/bootstrap/app-of-apps.yaml
   ```
   From here, every addon and app Argo CD manages
   (`infra/kubernetes/argocd/apps/*.yaml`) syncs itself — adding a file to that
   directory is enough to onboard something new.

## Layout reference

| Path | What |
|---|---|
| `terraform/bootstrap/` | One-time remote-state backend, applied with local state |
| `terraform/modules/` | Reusable building blocks (vpc, eks, irsa, storage, data, queues, secrets, ecr, waf) |
| `terraform/environments/{dev,staging,prod}/` | Composes the modules per environment — the only place `terraform apply` runs |
| `kubernetes/namespaces.yaml` | Every namespace, applied once, outside Helm/Argo CD's ownership |
| `kubernetes/addons/` | Helm `values.yaml` for third-party cluster add-ons (§2/§4/§7 of the architecture doc) |
| `kubernetes/addons/karpenter/nodepools/` | The actual NodePool/EC2NodeClass CRDs — plain manifests, not Helm, since they change far more often than the controller itself |
| `kubernetes/apps/{api,worker,qdrant,ingress}/` | This app's own manifests — Kustomize `base/` + per-environment `overlays/` |
| `kubernetes/argocd/` | The GitOps layer tying all of the above together |
| `scripts/` | Small operator scripts (see below) |

## Placeholders

Every value Terraform doesn't know until `apply`, or that depends on a real domain/
Slack webhook/git remote that doesn't exist yet, is left as an explicit
`REPLACE_WITH_...` string rather than a guess. Find them all with:

```bash
grep -rn "REPLACE_WITH_\|REPLACE_ME" infra/ Dockerfile
```

## What's infra-ready but not yet implemented in `app/`

- `infra/kubernetes/apps/worker/base/deployment.yaml` runs `python -m app.worker`,
  which doesn't exist yet — see `docs/aws-architecture.md` §6/§12 (Phase 1). Until it
  does, don't sync the `worker` Argo CD Application; crawl/ingest keep running
  in-process inside the `api` pod exactly as `app/api/crawl.py`/`app/api/ingest.py` do
  today (Phase 0), which works fine at a single `api` replica.
- `infra/kubernetes/apps/api/base/servicemonitor.yaml` scrapes `/metrics`, which the
  FastAPI app doesn't expose yet (no Prometheus instrumentation wired into
  `app/main.py`).
- `infra/kubernetes/addons/observability/tempo/` is ready to receive traces, but
  nothing in `app/` emits OpenTelemetry spans yet.

None of these block Phase 0 — they're here so the infra side doesn't need revisiting
when the app side catches up.
