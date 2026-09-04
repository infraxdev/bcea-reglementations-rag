from __future__ import annotations

from pathlib import Path

from ..crawler.job_store import load_job_result
from ..crawler.models import ResourceStatus, ResourceType
from .chunk import SimpleChunker
from .embed import NotConfiguredEmbedder
from .interfaces import Chunker, Embedder, Normalizer, Parser
from .models import IndexResult
from .parse import DoclingParser
from .vector_store import QdrantVectorStore, VectorStore
from .vlm_normalize import NotConfiguredNormalizer

# Resource types Docling can meaningfully parse. Video/audio/image/other resources from a
# crawl aren't handled by this pipeline (they'd need a transcription/captioning stage first).
_PARSEABLE_TYPES = {ResourceType.PDF, ResourceType.DOC, ResourceType.HTML}


async def index_crawl_job(
    job_id: str,
    parser: Parser | None = None,
    normalizer: Normalizer | None = None,
    chunker: Chunker | None = None,
    embedder: Embedder | None = None,
    vector_store: VectorStore | None = None,
) -> IndexResult:
    """Indexing · offline, end to end: reads a completed crawl's manifest and runs every
    downloaded document through Parse -> VLM normalize (if scanned) -> Chunk -> Embed -> Qdrant.

    Defaults to the real DoclingParser/QdrantVectorStore/SimpleChunker and the
    not-yet-configured Normalizer/Embedder stubs — pass concrete implementations in once
    you've picked a VLM and an embedding model.
    """
    parser = parser or DoclingParser()
    normalizer = normalizer or NotConfiguredNormalizer()
    chunker = chunker or SimpleChunker()
    embedder = embedder or NotConfiguredEmbedder()
    vector_store = vector_store or QdrantVectorStore()

    job = load_job_result(job_id)
    if job is None:
        raise ValueError(f"No crawl job found for job_id={job_id!r}")

    result = IndexResult(job_id=job_id)
    collection_ready = False

    for resource in job.resources:
        if resource.status != ResourceStatus.DOWNLOADED or resource.resource_type not in _PARSEABLE_TYPES:
            continue
        if not resource.storage_location or resource.storage_location.startswith("s3://"):
            # Docling reads local files. Indexing straight from S3 would need downloading
            # the object first — not implemented here since the crawler's default storage
            # backend is local disk; add that download step if you index S3-backed jobs.
            result.errors.append(f"{resource.url}: cannot parse non-local storage_location {resource.storage_location!r}")
            continue

        try:
            path = Path(resource.storage_location)
            document = await parser.parse(path, source_url=resource.url, source_location=resource.storage_location)

            if document.needs_normalization:
                normalized_pages = []
                for page in document.pages:
                    normalized_pages.append(page if page.has_text_layer else await normalizer.normalize(path, page))
                document = document.model_copy(update={"pages": normalized_pages})

            chunks = chunker.chunk(document)
            if not chunks:
                continue

            embedded = await embedder.embed_chunks(chunks)
            if not collection_ready and embedded:
                await vector_store.ensure_collection(vector_size=len(embedded[0].dense_vector))
                collection_ready = True
            await vector_store.upsert(embedded)

            result.documents_processed += 1
            result.chunks_indexed += len(embedded)
        except Exception as exc:
            result.errors.append(f"{resource.url}: {exc}")

    return result
