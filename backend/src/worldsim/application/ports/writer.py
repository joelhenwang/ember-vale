"""Writing port: a prompt in, a model's answer out (library writing help)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Written:
    text: str
    model: str
    seconds: float
    cost_usd: float


class WritingError(Exception):
    """The writer could not answer (service down, empty answer)."""


class Writer(Protocol):
    async def write(self, prompt: str) -> Written: ...
