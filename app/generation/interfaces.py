from __future__ import annotations

from abc import ABC, abstractmethod

from ..retrieval.models import ChatTurn
from .models import PolicyGateResult


class Generator(ABC):
    """LLM box: produces a grounded answer from a system prompt plus a multi-turn message
    list (prior conversation turns, oldest first, ending in the current user turn whose
    content is the assembled RAG prompt from retrieval/prompt_assembly.py)."""

    @abstractmethod
    async def generate(self, system: str, messages: list[ChatTurn]) -> str: ...


class PolicyGate(ABC):
    """Policy gate box: checks and redacts a generated answer before it's returned."""

    @abstractmethod
    def check(self, query: str, answer: str, has_context: bool) -> PolicyGateResult: ...
