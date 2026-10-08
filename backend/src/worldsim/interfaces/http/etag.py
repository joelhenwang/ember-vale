"""Revalidated JSON reads: an unchanged answer travels as a bare 304.

The player screen polls the same reads every few seconds (presentation,
chronicle, autoplay; ~35 requests per idle 80 s, perf-frontend-001). Each
successful JSON GET gets a content hash as its ETag and
``Cache-Control: private, no-cache``: the browser keeps the answer,
asks again with If-None-Match every time (never served stale), and an
unchanged answer comes back as 304 with no body. The fetch API turns that
into the cached 200 transparently, so the client code is unchanged.

``Vary`` names the role headers: a player and a watcher reading the same
URL must never share a cached answer. The handler still runs in full, so
permission checks are unchanged; only the bytes on the wire shrink.
"""

from __future__ import annotations

import hashlib

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

VARY = "Authorization, X-Worldsim-Role, X-Worldsim-Character"


class JsonETagMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return
        sent_tags = Headers(scope=scope).get("if-none-match", "")
        start: Message | None = None
        body: list[bytes] = []
        passthrough = False

        async def capture(message: Message) -> None:
            nonlocal start, passthrough
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.start":
                headers = Headers(raw=message["headers"])
                eligible = (
                    message["status"] == 200
                    and headers.get("content-type", "").startswith("application/json")
                    and "etag" not in headers
                    and "cache-control" not in headers
                )
                if not eligible:
                    passthrough = True
                    await send(message)
                    return
                start = message
                return
            if message["type"] == "http.response.body":
                body.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                assert start is not None
                payload = b"".join(body)
                tag = f'W/"{hashlib.blake2b(payload, digest_size=12).hexdigest()}"'
                headers = MutableHeaders(scope=start)
                headers["ETag"] = tag
                headers["Cache-Control"] = "private, no-cache"
                headers["Vary"] = VARY
                if tag in {t.strip() for t in sent_tags.split(",")}:
                    start["status"] = 304
                    del headers["content-length"]
                    if "content-type" in headers:
                        del headers["content-type"]
                    await send(start)
                    await send({"type": "http.response.body", "body": b""})
                    return
                headers["content-length"] = str(len(payload))
                await send(start)
                await send({"type": "http.response.body", "body": payload})

        await self.app(scope, receive, capture)
