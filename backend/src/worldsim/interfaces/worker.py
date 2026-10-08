"""Background loops in their own process: autoplay, painting, local indexing.

The API runs these itself by default. To scale the HTTP side to several
processes, run the API with ``WORLDSIM_APP__BACKGROUND_LOOPS=false`` and
``WORLDSIM_APP__WORKERS=N``, and one (or more) of these beside it:

    python -m worldsim.interfaces.worker

Every loop is safe beside a second copy: autoplay claims a story with a
lease, and image jobs are claimed with ``FOR UPDATE SKIP LOCKED``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from worldsim.infrastructure.http_pool import aclose_pooled
from worldsim.infrastructure.ops.logging import install
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import start_loops
from worldsim.interfaces.http.state import build_state

_log = logging.getLogger("worldsim.worker")


async def run(stop: asyncio.Event | None = None) -> None:
    """Run the loops until ``stop`` is set (or SIGINT/SIGTERM)."""
    settings = Settings()
    install(settings)
    state = build_state(settings)
    stop = stop or asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(sig, stop.set)  # not on Windows: Ctrl+C still ends it
    loops = start_loops(state)
    running = [type(job).__name__ for job, _ in loops.tasks]
    _log.info("worker running: %s", ", ".join(running) or "nothing switched on")
    try:
        await stop.wait()
    finally:
        await loops.stop()
        await aclose_pooled()
        await state.engine.dispose()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
