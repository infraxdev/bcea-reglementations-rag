from __future__ import annotations

from abc import ABC, abstractmethod

from .models import PolicyGateResult


class Generator(ABC):
    """LLM box: produces a grounded answer from an already-assembled prompt
    (context + citations, from retrieval/prompt_assembly.py)."""

    @abstractmethod
    async def generate(self, prompt: str) -> str: ...


class PolicyGate(ABC):
    """Policy gate box: checks and redacts a generated answer before it's returned."""

    @abstractmethod
    def check(self, query: str, answer: str, has_context: bool) -> PolicyGateResult: ...
