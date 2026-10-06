"""The player's words around every storyteller prompt of one story.

A story's ``llm_prefix`` and ``llm_suffix`` (Story settings) wrap the
user prompt of every model call the story's turns make: characters,
reactions, the resolver, the narrator, the director and day summaries.
The prefix goes first so the provider's prompt cache still matches
across calls (it is the same for the whole story); the system prompt is
left alone, so every role keeps its own instructions and output format.
"""

from __future__ import annotations

from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    ModelGateway,
    ProbeResult,
)
from worldsim.domain.story_prompts import framed


class FramedGateway:
    """A gateway whose completion prompts carry the story's additions."""

    def __init__(self, inner: ModelGateway, prefix: str, suffix: str) -> None:
        self._inner = inner
        self._prefix = prefix
        self._suffix = suffix
        self.profile = inner.profile

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        prompt = framed(self._prefix, request.prompt, self._suffix, joiner="\n\n")
        return await self._inner.complete(request.model_copy(update={"prompt": prompt}))

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return await self._inner.embed(request)

    async def probe(self) -> ProbeResult:
        return await self._inner.probe()

    def __getattr__(self, name: str) -> object:
        # Anything else (adapter details some callers read) is the inner gateway's.
        return getattr(self._inner, name)


def frame_gateways(
    gateways: dict[str, ModelGateway], prefix: str, suffix: str
) -> dict[str, ModelGateway]:
    """Every role's gateway framed; unchanged when the story adds nothing."""
    if not prefix.strip() and not suffix.strip():
        return gateways
    return {role: FramedGateway(gateway, prefix, suffix) for role, gateway in gateways.items()}
