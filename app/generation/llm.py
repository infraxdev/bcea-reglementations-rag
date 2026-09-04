from __future__ import annotations

from .interfaces import Generator


class NotConfiguredGenerator(Generator):
    """Default Generator — no LLM provider has been chosen yet.

    TODO: implement against your chosen provider (e.g. the Anthropic Messages API) and
    wire it into generation/pipeline.py in place of this class.
    """

    async def generate(self, prompt: str) -> str:
        raise NotImplementedError(
            "No generation LLM configured. Implement app.generation.llm.Generator against "
            "a provider and use it in generation/pipeline.py."
        )
