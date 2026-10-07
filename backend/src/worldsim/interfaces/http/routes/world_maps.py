"""World maps: bring a map picture, read its places and roads, time the roads.

A map picture is an unscoped MAP asset (served by /library/assets/{id}/bytes)
until a world preset pins its places on it. Reading asks vision models
on OpenRouter, so it costs money: the answer says how much.
"""

from __future__ import annotations

import base64
import binascii
import io
from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Request
from PIL import Image

from worldsim.application.geography import (
    DrawnRoad,
    PinnedPlace,
    spots_with_keys,
    world_with_map,
    world_with_place_map,
)
from worldsim.application.images import image_request
from worldsim.application.ports.images import ImageGenerationError
from worldsim.application.ports.map_reader import MapReader, MapReadingError, ReadPlace
from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.geography import PlaceMap, TravelScale
from worldsim.domain.ids import new_asset_id
from worldsim.domain.presets import (
    PresetKind,
    PresetRevision,
    WorldPresetPayload,
    canonical_payload_hash,
)
from worldsim.domain.settings import IMAGE_RATIOS
from worldsim.domain.time import utcnow
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.library import preset_detail
from worldsim.interfaces.http.routes.settings import OPERATOR

router = APIRouter(tags=["library"])

_MIMES = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}
#: A map wider or taller than this is kept but never needed.
MAX_PIXELS = 64_000_000
STYLE = "world-map"


def _storage(request: Request) -> LocalStorage:
    return LocalStorage(request.app.state.app_state.seed_dir.parent.parent / "assets")


async def _keep(request: Request, data: bytes) -> api.MapImageView:
    """Store a map picture as an unscoped MAP asset."""
    try:
        with Image.open(io.BytesIO(data)) as picture:
            fmt, (width, height) = picture.format or "", picture.size
            picture.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "that is not a picture") from exc
    if fmt not in _MIMES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "maps must be PNG, JPEG or WebP")
    if width * height > MAX_PIXELS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "that map is too large")
    mime, ext = _MIMES[fmt]
    asset_id = new_asset_id()
    ref = f"generated/maps/{asset_id}.{ext}"
    await _storage(request).write(ref, data, mime)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.assets.add_asset(
            AssetRecord(
                id=asset_id,
                kind=AssetKind.MAP,
                content_ref=ref,
                mime=mime,
                width=width,
                height=height,
                style_pack_version=STYLE,
            )
        )
        await uow.commit()
    return api.MapImageView(asset_id=asset_id, width=width, height=height)


async def _map_bytes(request: Request, asset_id: UUID) -> tuple[AssetRecord, bytes]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        asset = await uow.assets.get_asset(asset_id)
    if asset.kind != AssetKind.MAP or asset.world_id is not None:
        raise DomainError(ErrorCode.NOT_FOUND, "no such map picture")
    try:
        return asset, await _storage(request).read(asset.content_ref)
    except (FileNotFoundError, OSError) as exc:
        raise DomainError(ErrorCode.NOT_FOUND, "stored bytes are missing") from exc


def _reader(request: Request) -> MapReader:
    reader = request.app.state.app_state.map_reader()
    if reader is None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "no map reader: set WORLDSIM_PROVIDER__OPENROUTER_API_KEY",
        )
    return reader


@router.post("/library/maps", response_model=api.MapImageView)
async def upload_map(body: api.MapUploadRequest, request: Request) -> api.MapImageView:
    header, _, encoded = body.data_url.partition(",")
    if not header.startswith("data:image/") or ";base64" not in header:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "send the map as a base64 data URL")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "the data URL is not base64") from exc
    return await _keep(request, data)


@router.post("/library/maps/paint", response_model=api.MapImageView)
async def paint_map(body: api.MapPaintRequest, request: Request) -> api.MapImageView:
    state = request.app.state.app_state
    generator = state.images()
    if generator is None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "no image service: set WORLDSIM_IMAGES__PROVIDER=krea and KREA_BASE_URL",
        )
    if body.ratio not in IMAGE_RATIOS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"ratio must be one of {IMAGE_RATIOS}")
    async with state.uow_factory()() as uow:
        prefs = (await uow.settings.get_preferences(OPERATOR)).images
    try:
        made = await generator.generate(
            image_request(body.prompt, body.ratio, AssetKind.MAP, prefs)
        )
    except ImageGenerationError as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, f"image service: {exc}") from exc
    return await _keep(request, made.data)


@router.post("/library/maps/{asset_id}/places", response_model=api.MapPlacesView)
async def read_places(asset_id: UUID, request: Request) -> api.MapPlacesView:
    asset, data = await _map_bytes(request, asset_id)
    try:
        reading = await _reader(request).places(data, asset.mime)
    except MapReadingError as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, str(exc)) from exc
    return api.MapPlacesView(
        places=[api.MapPlaceView(name=p.name, kind=p.kind, point=p.point) for p in reading.found],
        model=reading.model,
        seconds=reading.seconds,
        cost_usd=reading.cost_usd,
    )


@router.post("/library/maps/{asset_id}/spots", response_model=api.MapPlacesView)
async def read_spots(asset_id: UUID, request: Request) -> api.MapPlacesView:
    """The spots inside one place, read off a closer picture of it."""
    asset, data = await _map_bytes(request, asset_id)
    try:
        reading = await _reader(request).spots(data, asset.mime)
    except MapReadingError as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, str(exc)) from exc
    return api.MapPlacesView(
        places=[api.MapPlaceView(name=p.name, kind=p.kind, point=p.point) for p in reading.found],
        model=reading.model,
        seconds=reading.seconds,
        cost_usd=reading.cost_usd,
    )


@router.post("/library/maps/{asset_id}/roads", response_model=api.MapRoadsView)
async def read_roads(
    asset_id: UUID, body: api.MapRoadsRequest, request: Request
) -> api.MapRoadsView:
    asset, data = await _map_bytes(request, asset_id)
    places = [ReadPlace(name=p.name, kind=p.kind, point=p.point) for p in body.places]
    try:
        reading = await _reader(request).roads(data, asset.mime, places)
    except MapReadingError as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, str(exc)) from exc
    return api.MapRoadsView(
        roads=[
            api.MapRoadView(a=r.a, b=r.b, by=r.by, points=list(r.points)) for r in reading.found
        ],
        model=reading.model,
        seconds=reading.seconds,
        cost_usd=reading.cost_usd,
    )


async def _revise_world(
    request: Request,
    preset_id: UUID,
    expected_version: int,
    change: Callable[[WorldPresetPayload], WorldPresetPayload],
) -> api.PresetDetail:
    """Write the world's next revision with one change applied."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        preset = await uow.presets.get_preset(preset_id)
        if preset.kind != PresetKind.WORLD:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "only worlds have maps")
        if preset.readonly:
            raise DomainError(ErrorCode.FORBIDDEN, "built-in worlds are read-only: duplicate it")
        current = await uow.presets.get_revision(preset_id, preset.current_revision)
        assert isinstance(current.payload, WorldPresetPayload)
        try:
            payload = change(current.payload)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid map: {exc}") from exc
        next_revision = preset.current_revision + 1
        await uow.presets.add_revision(
            PresetRevision(
                preset_id=preset_id,
                revision=next_revision,
                schema_version=1,
                payload=payload,
                content_hash=canonical_payload_hash(payload),
                created_at=utcnow(),
            )
        )
        await uow.presets.save_preset(
            preset.model_copy(update={"current_revision": next_revision}),
            expected_version,
        )
        await uow.commit()
    return await preset_detail(request, preset_id, next_revision)


@router.put("/library/presets/{preset_id}/map", response_model=api.PresetDetail)
async def save_world_map(
    preset_id: UUID, body: api.WorldMapRequest, request: Request
) -> api.PresetDetail:
    """Pin the world's places on the map and time its roads: a new revision."""
    asset, _ = await _map_bytes(request, body.asset_id)
    try:
        scale = TravelScale(
            shortest_phases=body.shortest_phases, longest_phases=body.longest_phases
        )
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, str(exc)) from exc
    return await _revise_world(
        request,
        preset_id,
        body.expected_version,
        lambda world: world_with_map(
            world,
            str(asset.id),
            asset.width,
            asset.height,
            [PinnedPlace(p.name, p.kind, p.point, p.key) for p in body.places],
            [DrawnRoad(r.a, r.b, r.by, tuple(r.points)) for r in body.roads],
            scale,
        ),
    )


@router.put("/library/presets/{preset_id}/places/{key}/map", response_model=api.PresetDetail)
async def save_place_map(
    preset_id: UUID, key: str, body: api.PlaceMapRequest, request: Request
) -> api.PresetDetail:
    """Give one place its own map and spots (or take it away): a new revision."""
    place_map: PlaceMap | None = None
    if body.asset_id is not None:
        asset, _ = await _map_bytes(request, body.asset_id)
        try:
            place_map = PlaceMap(
                asset_id=str(asset.id),
                width=asset.width,
                height=asset.height,
                spots=spots_with_keys([PinnedPlace(p.name, p.kind, p.point) for p in body.spots]),
            )
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid map: {exc}") from exc
    return await _revise_world(
        request,
        preset_id,
        body.expected_version,
        lambda world: world_with_place_map(world, key, place_map),
    )
