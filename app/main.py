from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .env import bootstrap

bootstrap()

from .api import crawl, ingest, query
from .config import get_cors_allowed_origins, get_job_settings
from .jobs import runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast on a bad JOB_* config instead of on the first POST /crawl.
    get_job_settings()
    yield
    await runtime.shutdown()


app = FastAPI(
    title="BCEAO Regulation RAG",
    description=(
        "Crawls BCEAO regulatory sources and serves a guarded-routing RAG pipeline over "
        "them: Sources -> Parse -> VLM normalize -> Chunk -> Embed -> Qdrant (indexing), "
        "then query router -> hybrid search -> rerank -> prompt assembly -> LLM -> policy "
        "gate (retrieval + generation)."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crawl.router)
app.include_router(ingest.router)
app.include_router(query.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
