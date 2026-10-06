"""Local model port: embeddings and entity spans from a service on this machine.

Both are optional helpers. Callers treat ``LocalModelsUnavailable`` as
"carry on without": recall falls back to recency and salience, and
grounding falls back to the word lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

EmbedKind = Literal["query", "document"]


class LocalModelsUnavailable(Exception):
    """The local service is off, still loading, slow or broken."""


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    model: str


@dataclass(frozen=True)
class Span:
    label: str
    text: str
    start: int
    end: int
    confidence: float


class LocalModels(Protocol):
    async def embed(self, texts: list[str], kind: EmbedKind) -> Embeddings: ...

    async def extract(
        self, texts: list[str], labels: dict[str, str], threshold: float = 0.5
    ) -> list[list[Span]]: ...
