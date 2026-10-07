"""Pictures a player brings for a character or a world: kept whole, framed by data.

A character's upload is an unscoped PORTRAIT asset (at most 2048 px a
side); the character preset keeps where its portrait and face are on it
(domain/framing.py). The face can be suggested by the map reader's model.
A world's is an unscoped BACKGROUND asset; the world preset keeps its
16:7 banner frame.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.ports.map_reader import MapReadingError
from worldsim.domain.assets import AssetKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.geography import MAP_SPAN
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.world_maps import (
    keep_picture,
    library_picture,
    map_reader,
    picture_bytes,
)

router = APIRouter(tags=["library"])

#: Imported portraits are shown on cards and tokens, never printed.
PORTRAIT_MAX_SIDE = 2048
#: World pictures fill wide banners.
COVER_MAX_SIDE = 2560


@router.post("/library/portraits", response_model=api.MapImageView)
async def upload_portrait(body: api.MapUploadRequest, request: Request) -> api.MapImageView:
    return await keep_picture(
        request,
        picture_bytes(body.data_url),
        kind=AssetKind.PORTRAIT,
        folder="portraits",
        style="imported-portrait",
        max_side=PORTRAIT_MAX_SIDE,
    )


@router.post("/library/covers", response_model=api.MapImageView)
async def upload_cover(body: api.MapUploadRequest, request: Request) -> api.MapImageView:
    return await keep_picture(
        request,
        picture_bytes(body.data_url),
        kind=AssetKind.BACKGROUND,
        folder="covers",
        style="imported-cover",
        max_side=COVER_MAX_SIDE,
    )


@router.post("/library/portraits/{asset_id}/face", response_model=api.FaceView)
async def find_face(asset_id: UUID, request: Request) -> api.FaceView:
    """The box around the character's face, as fractions of the picture."""
    asset, data = await library_picture(request, asset_id, AssetKind.PORTRAIT)
    try:
        reading = await map_reader(request).face(data, asset.mime)
    except MapReadingError as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, str(exc)) from exc
    face = None
    if reading.found:
        left, top, right, bottom = reading.found[0]
        face = [
            left / MAP_SPAN,
            top / MAP_SPAN,
            (right - left) / MAP_SPAN,
            (bottom - top) / MAP_SPAN,
        ]
    return api.FaceView(
        face=face, model=reading.model, seconds=reading.seconds, cost_usd=reading.cost_usd
    )
