from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .models import DocChunk, EmbeddedChunk, ParsedDocument, ParsedPage, QueryEmbedding


class Parser(ABC):
    """Sources -> Parse. Turns a downloaded file into page-level text."""

    @abstractmethod
    async def parse(self, path: Path, source_url: str, source_location: str) -> ParsedDocument: ...


class Normalizer(ABC):
    """VLM normalize. Re-extracts scanned pages (and tables) via a vision-capable model."""

    @abstractmethod
    async def normalize(self, path: Path, page: ParsedPage) -> ParsedPage: ...


class Chunker(ABC):
    """Chunk. Splits parsed pages into semantic + metadata-bearing chunks."""

    @abstractmethod
    def chunk(self, document: ParsedDocument) -> list[DocChunk]: ...


class Embedder(ABC):
    """Embed. Produces dense (+ optionally sparse) vectors for chunks and queries."""

    @abstractmethod
    async def embed_chunks(self, chunks: list[DocChunk]) -> list[EmbeddedChunk]: ...

    @abstractmethod
    async def embed_query(self, query: str) -> QueryEmbedding: ...
