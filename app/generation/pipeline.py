from __future__ import annotations

from ..retrieval.models import RetrievalResult
from .interfaces import Generator, PolicyGate
from .llm import NotConfiguredGenerator
from .models import GenerationResult
from .policy_gate import BasicPolicyGate

_OUT_OF_SCOPE_ANSWER = (
    "This question is outside the scope of BCEAO/UEMOA banking regulation, which is what "
    "this assistant is grounded on, so I can't answer it."
)
_POLICY_BLOCKED_ANSWER = "The generated answer didn't pass the policy gate, so it's being withheld."


async def generate_answer(
    retrieval_result: RetrievalResult,
    generator: Generator | None = None,
    policy_gate: PolicyGate | None = None,
) -> GenerationResult:
    """Generation, end to end: out-of-scope queries are refused with no LLM call (mirroring
    the router's decision from retrieval/pipeline.py); in-scope queries go LLM -> policy
    gate -> response."""
    if not retrieval_result.in_scope:
        return GenerationResult(query=retrieval_result.query, in_scope=False, answer=_OUT_OF_SCOPE_ANSWER)

    generator = generator or NotConfiguredGenerator()
    policy_gate = policy_gate or BasicPolicyGate()

    raw_answer = await generator.generate(retrieval_result.prompt or "")
    policy = policy_gate.check(retrieval_result.query, raw_answer, has_context=bool(retrieval_result.hits))
    answer = raw_answer if policy.passed else _POLICY_BLOCKED_ANSWER

    return GenerationResult(
        query=retrieval_result.query,
        in_scope=True,
        answer=answer,
        sources=retrieval_result.hits,
        policy=policy,
    )
