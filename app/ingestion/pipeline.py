from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path, PurePosixPath

from ..crawler.job_store import load_job_result
from ..crawler.models import CrawlResult, ResourceRecord, ResourceStatus, ResourceType
from . import progress as progress_store
from .chunk import SemanticChunker, SimpleChunker
from .embed import FastEmbedEmbedder
from .interfaces import Chunker, Embedder, Normalizer, Parser
from .models import IndexResult
from .parse import DoclingParser
from .vector_store import QdrantVectorStore, VectorStore
from .vlm_normalize import PassthroughNormalizer

# Resource types Docling can meaningfully parse. Video/audio/image/other resources from a
# crawl aren't handled by this pipeline (they'd need a transcription/captioning stage first).
_PARSEABLE_TYPES = {ResourceType.PDF, ResourceType.DOC, ResourceType.HTML}

# Name of the subfolder (created alongside each source file) that a document is moved
# into once it's fully indexed. Doubles as the resume checkpoint: a re-run of the same
# job skips anything already sitting in processed/ instead of reprocessing it, so an
# interrupted run (killed process, closed terminal) can just be re-started as-is.
_PROCESSED_DIRNAME = "processed"


def _candidate_resources(job: CrawlResult) -> list[ResourceRecord]:
    return [
        r
        for r in job.resources
        if r.status == ResourceStatus.DOWNLOADED and r.resource_type in _PARSEABLE_TYPES
    ]


@lru_cache(maxsize=1)
def _s3_client():
    from ..config import get_s3_storage_settings
    from ..crawler.storage.s3 import build_s3_client

    return build_s3_client(get_s3_storage_settings())


class _SourceFile:
    """One downloaded resource, wherever the crawler stored it. Moving a file into a
    sibling processed/ folder is the resume checkpoint (see _PROCESSED_DIRNAME):

    - local path: rename into <dir>/processed/<name>.
    - s3://bucket/key: copy to <dir>/processed/<name>, then delete the original. Parsing
      happens on a temporary local copy, since Docling reads local files.
    """

    def __init__(self, location: str):
        self.location = location
        self.is_s3 = location.startswith("s3://")
        if self.is_s3:
            from ..crawler.storage.s3 import parse_s3_uri

            self.bucket, self.key = parse_s3_uri(location)
            key = PurePosixPath(self.key)
            self.processed_key = str(key.parent / _PROCESSED_DIRNAME / key.name)
            self._client = _s3_client()
        else:
            self.path = Path(location)
            self.processed_path = self.path.parent / _PROCESSED_DIRNAME / self.path.name

    def _s3_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self._client.exceptions.ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def exists(self) -> bool:
        return self._s3_exists(self.key) if self.is_s3 else self.path.exists()

    def is_processed(self) -> bool:
        return self._s3_exists(self.processed_key) if self.is_s3 else self.processed_path.exists()

    def processed_location(self) -> str:
        return f"s3://{self.bucket}/{self.processed_key}" if self.is_s3 else str(self.processed_path)

    @asynccontextmanager
    async def local_copy(self) -> AsyncIterator[Path]:
        if not self.is_s3:
            yield self.path
            return
        tmp_dir = Path(tempfile.mkdtemp(prefix="ingest-"))
        try:
            # Keep the original file name: Docling picks its parser from the extension.
            local = tmp_dir / PurePosixPath(self.key).name
            await asyncio.to_thread(self._client.download_file, self.bucket, self.key, str(local))
            yield local
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def mark_processed(self) -> None:
        if self.is_s3:
            self._client.copy_object(
                Bucket=self.bucket,
                Key=self.processed_key,
                CopySource={"Bucket": self.bucket, "Key": self.key},
            )
            self._client.delete_object(Bucket=self.bucket, Key=self.key)
        else:
            self.processed_path.parent.mkdir(parents=True, exist_ok=True)
            self.path.rename(self.processed_path)


async def _count_already_processed(candidates: list[ResourceRecord]) -> int:
    """How many candidates a prior (possibly interrupted) run already moved into
    processed/. Computed upfront so a relaunch's first progress read reflects that work
    immediately, instead of reporting 0 done until the main loop re-walks past them."""

    def check(resource: ResourceRecord) -> bool:
        if not resource.storage_location:
            return False
        source = _SourceFile(resource.storage_location)
        return not source.exists() and source.is_processed()

    count = 0
    for resource in candidates:
        if await asyncio.to_thread(check, resource):
            count += 1
    return count


async def index_crawl_job(
    job_id: str,
    parser: Parser | None = None,
    normalizer: Normalizer | None = None,
    chunker: Chunker | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
) -> IndexResult:
    """Indexing · offline, end to end: reads a completed crawl's manifest and runs every
    downloaded document through Parse -> VLM normalize (if scanned) -> Chunk -> Embed ->
    Qdrant -> move source file into processed/. Publishes live progress to
    ingestion/progress.py as it goes (see GET /ingest/{job_id}/progress).

    Defaults to the real DoclingParser/FastEmbedEmbedder/QdrantVectorStore/SemanticChunker
    and a passthrough Normalizer (indexes whatever thin/garbled text Docling + RapidOCR
    already extracted rather than blocking the document) — pass a concrete VLM-backed
    implementation in once you want to compare index quality against that baseline.
    """
    parser = parser or DoclingParser()
    normalizer = normalizer or PassthroughNormalizer()
    chunker = chunker or SemanticChunker()
    embedder = embedder or FastEmbedEmbedder()
    vector_store = vector_store or QdrantVectorStore()

    job = load_job_result(job_id)
    if job is None:
        raise ValueError(f"No crawl job found for job_id={job_id!r}")

    candidates = _candidate_resources(job)
    already_done = await _count_already_processed(candidates)
    result = IndexResult(job_id=job_id, documents_skipped=already_done)
    collection_ready = False
    progress_store.start(job_id, total_documents=len(candidates), documents_skipped=already_done)

    try:
        for resource in candidates:
            progress_store.update(job_id, current_file=resource.url)

            if not resource.storage_location:
                result.errors.append(f"{resource.url}: no storage_location in the crawl manifest")
                progress_store.update(job_id, errors=result.errors)
                continue

            source = _SourceFile(resource.storage_location)
            if not await asyncio.to_thread(source.exists):
                if await asyncio.to_thread(source.is_processed):
                    # Already indexed and moved by a prior (possibly interrupted) run —
                    # already counted in `already_done` above, so just skip past it here.
                    continue
                result.errors.append(
                    f"{resource.url}: file not found at {source.location} "
                    f"(nor at {source.processed_location()})"
                )
                progress_store.update(job_id, errors=result.errors)
                continue

            try:
                async with source.local_copy() as path:
                    document = await parser.parse(
                        path, source_url=resource.url, source_location=resource.storage_location
                    )

                    if document.needs_normalization:
                        normalized_pages = []
                        for page in document.pages:
                            normalized_pages.append(
                                page if page.has_text_layer else await normalizer.normalize(path, page)
                            )
                        document = document.model_copy(update={"pages": normalized_pages})

                chunks = chunker.chunk(document)
                if chunks:
                    embedded = await embedder.embed_chunks(chunks)
                    if not collection_ready and embedded:
                        await vector_store.ensure_collection(vector_size=len(embedded[0].dense_vector))
                        collection_ready = True
                    await vector_store.upsert(embedded)
                    result.chunks_indexed += len(embedded)

                await asyncio.to_thread(source.mark_processed)

                result.documents_processed += 1
                progress_store.update(
                    job_id, documents_processed=result.documents_processed, chunks_indexed=result.chunks_indexed
                )
            except Exception as exc:
                result.errors.append(f"{resource.url}: {exc}")
                progress_store.update(job_id, errors=result.errors)
    finally:
        progress_store.update(job_id, status="completed", current_file=None)

    return result
