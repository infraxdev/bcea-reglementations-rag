from __future__ import annotations

from fastapi import FastAPI

from .api import crawl, ingest, query

app = FastAPI(
    title="BCEAO Regulation RAG",
    description=(
        "Crawls BCEAO regulatory sources and serves a guarded-routing RAG pipeline over "
        "them: Sources -> Parse -> VLM normalize -> Chunk -> Embed -> Qdrant (indexing), "
        "then query router -> hybrid search -> rerank -> prompt assembly -> LLM -> policy "
        "gate (retrieval + generation)."
    ),
    version="2.0.0",
)

app.include_router(crawl.router)
app.include_router(ingest.router)
app.include_router(query.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
