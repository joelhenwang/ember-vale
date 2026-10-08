"""HTTP caching for stored pictures.

An asset's bytes never change under its id (a new painting is a new
asset), so a browser may keep them for a year and revalidate by ETag.
"private": what a viewer may see depends on their role, so shared caches
must not keep it. Permission checks still run before a 304 is answered.
"""

from __future__ import annotations

from fastapi import Request, Response

from worldsim.domain.assets import AssetRecord

IMMUTABLE = "private, max-age=31536000, immutable"


def etag_for(asset: AssetRecord) -> str:
    return f'"{asset.id.hex}"'


def not_modified(request: Request, asset: AssetRecord) -> Response | None:
    """A 304 when the browser already holds these bytes, else None."""
    tag = etag_for(asset)
    sent = request.headers.get("if-none-match", "")
    tags = {t.strip().removeprefix("W/") for t in sent.split(",") if t.strip()}
    if tag in tags or "*" in tags:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": IMMUTABLE})
    return None


def asset_response(asset: AssetRecord, data: bytes) -> Response:
    return Response(
        content=data,
        media_type=asset.mime,
        headers={"ETag": etag_for(asset), "Cache-Control": IMMUTABLE},
    )
