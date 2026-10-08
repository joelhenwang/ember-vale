"""API key enforcement (owned by S5-HARD-001).

Startup refuses a public bind without a key; this middleware is the
other half: when a key is configured, every request outside the
health probes must bear it. No key configured means local loopback
development, and everything stays open.
"""

from __future__ import annotations

import secrets

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from worldsim.interfaces.http.errors import envelope

EXEMPT_PATHS = frozenset({"/api/v1/health/live", "/api/v1/health/ready"})


class ApiKeyMiddleware:
    """Pure ASGI (no BaseHTTPMiddleware): no extra task or body buffering
    per request, which capped simple routes at ~250 requests/s."""

    def __init__(self, app: ASGIApp, expected_key: str | None) -> None:
        self.app = app
        self._expected = expected_key.encode() if expected_key else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._expected or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        presented = b""
        for name, value in scope["headers"]:
            if name == b"authorization":
                presented = value
                break
        scheme, _, token = presented.partition(b" ")
        if scheme.lower() != b"bearer" or not secrets.compare_digest(token, self._expected):
            request_id = str(scope.get("state", {}).get("request_id", ""))
            response = JSONResponse(
                status_code=401,
                content=envelope("UNAUTHORIZED", "valid bearer key required", request_id, {}),
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
