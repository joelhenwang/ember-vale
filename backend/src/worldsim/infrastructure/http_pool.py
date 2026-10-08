"""One pooled HTTP client per event loop, shared by every outbound adapter.

Building an ``httpx.AsyncClient`` loads a fresh SSL context (~25 ms of CPU
on the event loop) and every new client opens its own TCP+TLS connection
(~50 ms to OpenRouter, measured 2026-10-08, docs/evidence/perf-beat-001).
A beat makes 20-60 model calls, so per-call clients cost seconds of
blocking CPU and handshakes. Adapters take this shared client instead and
pass their own timeout on each request.

The client is keyed by the running loop: a connection pool must not cross
event loops (tests run many ``asyncio.run`` loops in one process). The
app's lifespan closes it on shutdown (``aclose_pooled``).
"""

from __future__ import annotations

import asyncio
import weakref

import httpx

#: Keep-alive pool sized for a beat's parallel bursts (decisions and
#: reactions for a large cast run side by side).
LIMITS = httpx.Limits(max_connections=64, max_keepalive_connections=32, keepalive_expiry=60.0)

_CLIENTS: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)


def pooled_client() -> httpx.AsyncClient:
    """The shared client for the running event loop (created on first use)."""
    loop = asyncio.get_running_loop()
    client = _CLIENTS.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(limits=LIMITS, timeout=30.0)
        _CLIENTS[loop] = client
    return client


async def aclose_pooled() -> None:
    """Close the running loop's shared client, if one was made."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    client = _CLIENTS.pop(loop, None)
    if client is not None:
        await client.aclose()
