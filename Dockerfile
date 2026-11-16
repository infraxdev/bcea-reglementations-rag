# syntax=docker/dockerfile:1
#
# One image, two roles — matches docs/aws-architecture.md §6/§10: the API Deployment
# runs this with the default CMD (uvicorn), the worker Deployment overrides `command`
# to run `python -m app.worker` instead. Build once, push once, deploy twice.
#
# Build:  docker build -t bceao-rag:<tag> .
# Run api:    docker run -p 8000:8000 --env-file .env bceao-rag:<tag>
# Run worker: docker run --env-file .env bceao-rag:<tag> python -m app.worker

ARG PYTHON_VERSION=3.11

# ---------------------------------------------------------------------------
# deps: install Python dependencies in their own layer so app code edits don't
# bust the pip-install cache.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS deps

# libgl1/libglib2.0-0: RapidOCR's OpenCV dependency (app/ingestion/parse.py's
# docling[rapidocr] extra). curl: container HEALTHCHECK + /health probe.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
# CPU-only PyTorch first. Docling's layout/table models need torch + torchvision, but
# the default PyPI wheel is the CUDA build (~4-5 GB of nvidia/ + triton libraries).
# Nothing here runs on a GPU: the ingest-worker and api node pools are CPU instances,
# and embeddings/reranking/OCR use ONNX Runtime. requirements.txt then finds torch
# already satisfied and keeps this build. The assert fails the build if a CUDA wheel
# ever comes back (e.g. a dependency pinning a torch version the CPU index lacks).
# --retries/--timeout: still a large download; one dropped connection shouldn't fail it.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --retries 10 --timeout 120 --upgrade pip \
  && pip install --no-cache-dir --retries 10 --timeout 120 --index-url "${TORCH_INDEX_URL}" torch torchvision \
  && pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt \
  && python -c "import torch; assert torch.version.cuda is None, f'CUDA torch installed: {torch.__version__}'; print('torch', torch.__version__)"
# Needed here (not just in the runtime stage) so the `models` stage below can import
# app.ingestion.embed / app.retrieval.rerank's model-name constants.
COPY app/ ./app/

# ---------------------------------------------------------------------------
# models: pre-download the fastembed/rerank ONNX weights and Docling's layout, table
# and OCR models at build time and bake them into the image, per docs/aws-architecture.md §3 — "bake into the image
# instead of a mounted volume" avoids a multi-GB re-download from HuggingFace on
# every pod cold start, which matters once Karpenter/KEDA are scaling pods up and
# down on demand.
# ---------------------------------------------------------------------------
FROM deps AS models

# HF_HOME: Docling's layout/table models (HuggingFace hub cache). RapidOCR's models go
# into site-packages/rapidocr/models/, which is why the runtime stage copies
# site-packages from this stage rather than from `deps`.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache \
    HF_HOME=/opt/hf_home
RUN mkdir -p "${FASTEMBED_CACHE_PATH}" "${HF_HOME}"

COPY docker/warm_models.py ./warm_models.py
RUN python warm_models.py && rm warm_models.py

# ---------------------------------------------------------------------------
# runtime: final image — app code + baked model cache, non-root user.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

# From `models`, not `deps`: same packages plus RapidOCR's downloaded models.
COPY --from=models /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
# --chown at copy time: a later `RUN chown -R` would rewrite every file into a new layer,
# storing the multi-GB model caches twice.
COPY --from=models --chown=appuser:appuser /opt/fastembed_cache /opt/fastembed_cache
COPY --from=models --chown=appuser:appuser /opt/hf_home /opt/hf_home

# HF_HUB_OFFLINE: every model is baked in, so never call the HuggingFace hub at runtime
# (no cold-start downloads, no revision checks through the NAT gateway). A model missing
# from the image then fails loudly instead of silently downloading.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache \
    HF_HOME=/opt/hf_home \
    HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=appuser:appuser app/ ./app/

# data/ (local crawl storage) and job_metadata/ (local crawl manifests) are mount points
# for compose.yml's shared volumes. Creating them here, owned by appuser, makes Docker
# initialise fresh named volumes with that ownership, so the non-root user can write.
RUN mkdir -p /app/data /app/job_metadata \
  && chown appuser:appuser /app /app/data /app/job_metadata
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# The worker runs the same image with `python -m app.worker` instead
# (infra/kubernetes/apps/worker/base/deployment.yaml, compose.yml's `worker` service).
# It has no HTTP server, so it disables this image's HEALTHCHECK.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
