"""Compile each role graph once; bind the call's dependencies at invoke time.

``StateGraph.compile()`` inspects every node function (signatures, source
parsing for nonlocals, type hints): 17-90 ms of CPU per graph on the event
loop, and the orchestrator built a fresh graph for every decision,
reaction, resolution and narration, about 45 a beat with three characters
(docs/evidence/perf-beat-001). The graphs differ only in the ``deps`` their
nodes close over, never in shape: builders read ``deps`` inside nodes only.

``compile_once`` compiles a builder a single time against a stand-in whose
attributes read the current call's deps from a ContextVar; the returned
``BoundGraph`` sets that var around ``ainvoke``. LangGraph runs nodes in
tasks and executor threads that copy the caller's context, and concurrent
calls each set the var in their own task, so calls never see each other's
deps.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any


class _CallDeps:
    """Stands in for ``deps`` inside the shared graph: reads the call's own."""

    def __init__(self, var: ContextVar[Any]) -> None:
        self._var = var

    def __getattr__(self, name: str) -> Any:
        return getattr(self._var.get(), name)


class BoundGraph:
    """The shared compiled graph with one call's deps bound around ``ainvoke``."""

    def __init__(self, compiled: Any, var: ContextVar[Any], deps: Any) -> None:
        self._compiled = compiled
        self._var = var
        self._deps = deps

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        token = self._var.set(self._deps)
        try:
            return await self._compiled.ainvoke(*args, **kwargs)
        finally:
            self._var.reset(token)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._compiled, name)


def compile_once[D](builder: Callable[[D], Any]) -> Callable[[D], BoundGraph]:
    """Decorate a ``build_*_graph(deps)`` so the graph compiles only once."""
    var: ContextVar[Any] = ContextVar(f"{builder.__name__}.deps")
    compiled: list[Any] = []

    @wraps(builder)
    def build(deps: D) -> BoundGraph:
        if not compiled:
            compiled.append(builder(_CallDeps(var)))  # type: ignore[arg-type]
        return BoundGraph(compiled[0], var, deps)

    return build
