from __future__ import annotations

from ..config import GenerationConfigError, get_generation_settings
from ..retrieval.models import ChatTurn
from .interfaces import Generator

_DEFAULT_MODELS = {
    "ollama": "qwen2.5:7b",
    "openai": "gpt-5",
    "anthropic": "claude-opus-5",
}
_REQUEST_TIMEOUT = 120.0  # local/self-hosted LLM generation can be slow, especially on CPU


def _merge_adjacent_same_role(messages: list[ChatTurn]) -> list[ChatTurn]:
    """Collapses consecutive same-role turns into one (joined by a blank line) and drops
    a leading assistant turn with no preceding user turn. Providers with strict
    user/assistant alternation (Anthropic) reject malformed sequences outright; this is
    cheap insurance against edge cases like a dropped/errored turn upstream."""
    merged: list[ChatTurn] = []
    for turn in messages:
        if not merged and turn.role != "user":
            continue
        if merged and merged[-1].role == turn.role:
            merged[-1] = ChatTurn(role=turn.role, content=f"{merged[-1].content}\n\n{turn.content}")
        else:
            merged.append(turn)
    return merged


class OllamaGenerator(Generator):
    """Local (or in-cluster) Ollama Generator — e.g. Qwen 2.5:7b. base_url defaults to
    http://localhost:11434 for local dev; override OLLAMA_BASE_URL to point at an
    in-cluster Ollama Service (e.g. a ClusterIP DNS name) when deployed to EKS."""

    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def generate(self, system: str, messages: list[ChatTurn]) -> str:
        import httpx

        payload_messages = [{"role": "system", "content": system}] + [
            {"role": turn.role, "content": turn.content} for turn in messages
        ]
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": payload_messages,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]


class OpenAIGenerator(Generator):
    """OpenAI (ChatGPT) Generator. Lazily imports the openai SDK so it's only required
    when this provider is actually selected."""

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def generate(self, system: str, messages: list[ChatTurn]) -> str:
        payload_messages = [{"role": "system", "content": system}] + [
            {"role": turn.role, "content": turn.content} for turn in messages
        ]
        response = await self._get_client().chat.completions.create(
            model=self.model,
            messages=payload_messages,
        )
        return response.choices[0].message.content or ""


class ClaudeGenerator(Generator):
    """Anthropic (Claude) Generator — defaults to Claude Opus 5. Lazily imports the
    anthropic SDK so it's only required when this provider is actually selected."""

    def __init__(self, model: str, api_key: str, max_tokens: int = 4096) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def generate(self, system: str, messages: list[ChatTurn]) -> str:
        # Anthropic's messages API takes the system prompt separately and requires the
        # messages list to start on "user" and strictly alternate roles.
        payload_messages = _merge_adjacent_same_role(messages)
        response = await self._get_client().messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": turn.role, "content": turn.content} for turn in payload_messages],
        )
        # Claude Opus 5's safety classifiers can decline a request outright (HTTP 200,
        # empty/partial content) rather than raising — surface that distinctly instead
        # of silently returning an empty answer.
        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to generate an answer for this prompt (safety refusal).")
        return "".join(block.text for block in response.content if block.type == "text")


def build_generator(provider: str | None = None, model: str | None = None) -> Generator:
    """Factory: builds a Generator for the requested provider ('ollama' | 'openai' |
    'anthropic'), defaulting to GENERATION_PROVIDER / GENERATION_MODEL from the
    environment (see .env.example). Pass provider/model explicitly to override per call
    — e.g. to A/B Qwen vs. ChatGPT vs. Claude on the same query without restarting
    the server."""
    settings = get_generation_settings()
    provider = (provider or settings.provider).strip().lower()
    model = model or (settings.model if provider == settings.provider else None) or _DEFAULT_MODELS.get(provider)

    if provider == "ollama":
        return OllamaGenerator(model=model or _DEFAULT_MODELS["ollama"], base_url=settings.ollama_base_url)
    if provider == "openai":
        if not settings.openai_api_key:
            raise GenerationConfigError("GENERATION_PROVIDER=openai but OPENAI_API_KEY is not set.")
        return OpenAIGenerator(model=model or _DEFAULT_MODELS["openai"], api_key=settings.openai_api_key)
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise GenerationConfigError("GENERATION_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        return ClaudeGenerator(model=model or _DEFAULT_MODELS["anthropic"], api_key=settings.anthropic_api_key)

    raise GenerationConfigError(f"Unknown GENERATION_PROVIDER={provider!r}. Supported: {sorted(_DEFAULT_MODELS)}.")
