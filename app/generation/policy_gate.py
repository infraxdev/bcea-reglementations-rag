from __future__ import annotations

import re

from .interfaces import PolicyGate
from .models import PolicyGateResult

_CITATION_MARKER_RE = re.compile(r"\[\d+\]")
_MAX_ANSWER_CHARS = 6000


class BasicPolicyGate(PolicyGate):
    """Default PolicyGate — a handful of deterministic, no-model-required checks:
    the answer isn't empty, isn't a runaway length, doesn't echo the system preamble
    back (a common prompt-leak symptom), and — when context was actually retrieved —
    cites at least one source. Redaction/PII checks and anything needing a model
    judge are TODOs on top of this, not replacements for it."""

    def check(self, query: str, answer: str, has_context: bool) -> PolicyGateResult:
        violations: list[str] = []

        if not answer or not answer.strip():
            violations.append("empty answer")
        if len(answer) > _MAX_ANSWER_CHARS:
            violations.append(f"answer exceeds {_MAX_ANSWER_CHARS} characters")
        if "regulatory assistant answering questions" in answer.lower():
            violations.append("answer appears to leak the system prompt")
        if has_context and not _CITATION_MARKER_RE.search(answer):
            violations.append("context was retrieved but answer has no [n] citation")

        return PolicyGateResult(passed=not violations, violations=violations)
