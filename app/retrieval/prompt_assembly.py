from __future__ import annotations

from ..ingestion.models import SearchHit

# Deterministic sentinel the model must open a reply with when the context doesn't
# contain the answer — checkable by generation/policy_gate.py, unlike free-form "I don't
# know" prose. Without this, BasicPolicyGate can't tell a legitimate "not in the
# documents" decline (which has no [n] citation, correctly) from an uncited hallucination
# (which also has no [n] citation), and withholds both.
NO_ANSWER_MARKER = "Information non trouvée dans les documents disponibles."

_SYSTEM_PREAMBLE = (
    "You are a regulatory assistant answering questions about BCEAO/UEMOA banking "
    "regulation using only the numbered context excerpts below. Cite every claim with "
    "the matching [n] marker — the [n] markers and the Sources list are the reader's "
    "only reference trail. Never refer to your own retrieval mechanism or describe the "
    "excerpts as \"the context\", \"the provided context/documents\", or similar — answer "
    "as a direct statement of fact backed by citations, the way the source law itself "
    "would be cited. Never name a source document's title or file name in the answer "
    "text itself (e.g. do not write \"according to the Loi bancaire...\") — the [n] "
    "marker alone is enough, since the reader can see the title by hovering or clicking it. "
    f"If the excerpts don't contain the answer, respond with "
    f'exactly this sentence, then a brief explanation, with no [n] citation: "{NO_ANSWER_MARKER}" '
    "Never guess."
)

# Small/local generation models (e.g. qwen2.5:7b via Ollama) follow the [n]-citation
# format far more reliably when shown one example of it than when only told the rule in
# prose — this one-shot example is what pushed BasicPolicyGate's citation check from
# failing to passing in testing. Clearly delimited and marked "illustrative" so the model
# doesn't mistake it for real context to cite from.
_EXAMPLE = """Example (illustrative only, not real context):
Context:
[1] Article 12 : Le capital social minimum des banques est fixé à 20 milliards de francs CFA.

Sources:
[1] Loi bancaire, article 12 — https://example.org/loi-bancaire.pdf

Question: Quel est le capital minimum requis pour une banque ?
Answer: Le capital social minimum requis pour une banque est de 20 milliards de francs CFA [1].

Example (illustrative only — shows the no-answer case):
Context:
[1] Article 12 : Le capital social minimum des banques est fixé à 20 milliards de francs CFA.

Sources:
[1] Loi bancaire, article 12 — https://example.org/loi-bancaire.pdf

Question: Quel est le nom de la plateforme de télédéclaration des réserves obligatoires ?
Answer: {no_answer_marker} Les documents disponibles traitent du capital social minimum, pas d'une plateforme de télédéclaration.
--- End of examples ---""".format(no_answer_marker=NO_ANSWER_MARKER)


_GENERAL_SYSTEM = (
    "You are the assistant of a service specialised in BCEAO/UEMOA banking regulation. "
    "The user's latest message is a general finance, banking or economics question that "
    "does not depend on the regulatory texts, so answer it directly from your own "
    "knowledge, clearly and concisely, using the conversation so far to understand what "
    "is being asked. No documents were retrieved for this answer: do not use [n] "
    "citation markers (earlier answers in the conversation may contain some; ignore "
    "them) and do not claim to quote any text. Do not state specific BCEAO/UEMOA "
    "regulatory figures, thresholds, obligations or sanctions from memory; if the answer "
    "would need them, explain the general concept and invite the user to ask what the "
    "regulation provides. Answer in the language of the user's latest message, French "
    "if unsure."
)


def assemble_general_system(history_summary: str | None = None) -> str:
    """System prompt for general finance questions answered without retrieval (see
    generation/pipeline.py), with the rolling conversation summary appended when one
    exists."""
    system = _GENERAL_SYSTEM
    if history_summary:
        system += f"\n\nSummary of earlier parts of this conversation (for context only):\n{history_summary}"
    return system


def assemble_system(history_summary: str | None = None) -> str:
    """System-prompt box: the fixed regulatory-assistant instructions and citation
    example, sent via each provider's native system role (see generation/llm.py) rather
    than concatenated into the user turn. Appends the rolling conversation summary (see
    generation/memory.py) when one exists, so older turns still inform the answer even
    after they've aged out of the verbatim message list."""
    system = f"{_SYSTEM_PREAMBLE}\n\n{_EXAMPLE}"
    if history_summary:
        system += (
            "\n\nSummary of earlier parts of this conversation (for context only, not "
            f"part of the retrieved documents, do not cite it):\n{history_summary}"
        )
    return system


def assemble_user_message(query: str, hits: list[SearchHit]) -> str:
    """Prompt assembly box: turns reranked hits into a context block with [n] citation
    markers plus a source list, and appends the user's question. This becomes the final
    entry in the multi-turn message list (see generation/pipeline.py) — purely string
    templating, no model call, so this works today independent of which LLM/embedder
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
        f"Now answer the following in the same style, using only the context below:\n\n"
        f"Context:\n{context}\n\n"
        f"Sources:\n{sources}\n\n"
        f"Question: {query}"
    )
