# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Role graphs compile once; each call still sees only its own deps."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import StateGraph

from worldsim.application.graphs.compiled import compile_once


class _State(TypedDict):
    n: int
    out: str


@dataclass(frozen=True)
class _Deps:
    label: str
    delay: float


compiles = 0


@compile_once
def _build(deps: _Deps) -> Any:
    global compiles
    compiles += 1

    async def slow(state: _State) -> dict[str, Any]:
        await asyncio.sleep(deps.delay)  # interleave the concurrent calls
        return {"out": f"{deps.label}:{state['n']}"}

    def sync_tail(state: _State) -> dict[str, Any]:  # runs in an executor thread
        return {"out": f"{state['out']}/{deps.label}"}

    builder = StateGraph(_State)
    builder.add_node("slow", slow)
    builder.add_node("tail", sync_tail)
    builder.set_entry_point("slow")
    builder.add_edge("slow", "tail")
    builder.set_finish_point("tail")
    return builder.compile()


def test_concurrent_calls_keep_their_own_deps_and_compile_once() -> None:
    async def _inner() -> list[str]:
        graphs = [_build(_Deps(f"g{i}", 0.02 * (5 - i))) for i in range(5)]
        results = await asyncio.gather(*(g.ainvoke({"n": i}) for i, g in enumerate(graphs)))
        return [r["out"] for r in results]

    assert asyncio.run(_inner()) == [f"g{i}:{i}/g{i}" for i in range(5)]
    assert compiles == 1
