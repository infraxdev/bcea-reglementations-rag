from __future__ import annotations

from ..ingestion.models import SearchHit

_SYSTEM_PREAMBLE = (
    "You are a regulatory assistant answering questions about BCEAO/UEMOA banking "
    "regulation using only the numbered context excerpts below. Cite every claim with "
    "the matching [n] marker. If the context doesn't contain the answer, say so instead "
    "of guessing."
)


def assemble_prompt(query: str, hits: list[SearchHit]) -> str:
    """Prompt assembly box: turns reranked hits into a context block with [n] citation
    markers plus a source list, and appends the user's question. Purely string
    templating — no model call — so this works today independent of which LLM/embedder
    ends up wired in."""
    context_blocks = []
    source_lines = []
    for i, hit in enumerate(hits, start=1):
        context_blocks.append(f"[{i}] {hit.text}")
        location = f"{hit.title or hit.source_url}" + (f", page {hit.page_number}" if hit.page_number else "")
        source_lines.append(f"[{i}] {location} — {hit.source_url}")

    context = "\n\n".join(context_blocks) if context_blocks else "(no matching context retrieved)"
    sources = "\n".join(source_lines) if source_lines else "(none)"

    return (
        f"{_SYSTEM_PREAMBLE}\n\n"
        f"Context:\n{context}\n\n"
        f"Sources:\n{sources}\n\n"
        f"Question: {query}"
    )
