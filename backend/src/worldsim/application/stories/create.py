"""Atomic new-story instantiation (owned by MAINMENU-A06).

One UoW transaction mints a fresh World, its locations, cast, version rows,
initial phase context, role grant, setup snapshot, catalog entry, draft
completion, and idempotency receipt. Any failure rolls everything back: no
partial playable story ever escapes. Curated art registers after the commit
through its own transaction, so a failed image job cannot sink a valid story.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from worldsim.application.geography import PLACE_MAPS
from worldsim.application.images import queue_image
from worldsim.application.library.builtins import WORLD_PRESET_ID
from worldsim.application.orchestration.stage1 import UnitOfWorkFactory
from worldsim.application.stories.validation import story_dnd_tables, validate_draft
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.activities import TravelRoute, focus_for_seat
from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.carried import carried_items
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import EventType, LifeStatus, PhaseName, PhaseRunState, UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.framing import Frame, as_list
from worldsim.domain.geography import MAP_SPAN, WorldMap, road_stamina
from worldsim.domain.ids import (
    new_asset_id,
    new_card_id,
    new_character_id,
    new_item_instance_id,
    new_location_id,
    new_party_member_id,
    new_role_grant_id,
    new_route_id,
    new_world_id,
)
from worldsim.domain.party import PartyMember, party_name_key
from worldsim.domain.phases import PhaseRun
from worldsim.domain.presets import (
    CharacterPresetPayload,
    WorldCover,
    WorldLocationPreset,
    WorldPresetPayload,
)
from worldsim.domain.progress import ItemInstance
from worldsim.domain.roles import RoleGrant
from worldsim.domain.rules.dnd import auto_sheet
from worldsim.domain.stories import (
    DraftCastMember,
    DraftPayload,
    SetupProvenance,
    StoryCatalogEntry,
    StoryCreationReceipt,
    StoryDraft,
    StoryInitialSetup,
)
from worldsim.domain.time import utcnow
from worldsim.domain.world import Location, Route, World

OPERATOR = "local"


@dataclass(frozen=True)
class CreateResult:
    story_id: UUID
    world_id: UUID
    role: str
    character_id: UUID | None
    replayed: bool


async def create_story(
    uow_factory: UnitOfWorkFactory,
    draft: StoryDraft,
    expected_draft_version: int,
    operator: str,
    idempotency_key: str,
) -> CreateResult:
    """Resolve a draft into a live story, atomically and idempotently."""
    payload = draft.payload
    issues = validate_draft(payload)
    if issues:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"draft is not creatable: {'; '.join(issues)}"
        )
    if not idempotency_key.strip():
        raise DomainError(ErrorCode.VALIDATION_FAILED, "idempotency key is required")
    request_hash = _request_hash(draft, expected_draft_version)
    async with uow_factory() as uow:
        existing = await uow.stories.find_receipt(operator, idempotency_key.strip())
        if existing is not None:
            if existing.request_hash != request_hash:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "idempotency key was used for a different request",
                )
            return await _replay(uow, existing)
        if draft.created_world_id is not None:
            # The winner may have committed between our receipt read and this
            # draft read: the same key replays, a different key is refused.
            raced = await uow.stories.find_receipt(operator, idempotency_key.strip())
            if raced is not None:
                if raced.request_hash != request_hash:
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "idempotency key was used for a different request",
                    )
                return await _replay(uow, raced)
            raise DomainError(ErrorCode.FORBIDDEN, "this draft already created a story")
        world_preset = await _world_preset(uow, payload)
        cast_presets = await _cast_presets(uow, payload)
        try:
            result = await _instantiate(
                uow, draft, expected_draft_version, world_preset, cast_presets
            )
        except DomainError as exc:
            if exc.code is not ErrorCode.VERSION_CONFLICT:
                raise
            # Our receipt read raced a concurrent commit: the same key replays
            # the winner; without a receipt this is a genuine conflict.
            await uow.rollback()
            async with uow_factory() as fresh:
                raced_after = await fresh.stories.find_receipt(operator, idempotency_key.strip())
            if raced_after is None:
                raise
            return await _replay_after_race(
                uow_factory, operator, idempotency_key.strip(), request_hash
            )
        try:
            await uow.stories.put_receipt(
                StoryCreationReceipt(
                    operator=operator,
                    idempotency_key=idempotency_key.strip(),
                    request_hash=request_hash,
                    created_world_id=result.world_id,
                    created_at=utcnow(),
                )
            )
            await uow.commit()
        except IntegrityError:
            await uow.rollback()
            return await _replay_after_race(
                uow_factory, operator, idempotency_key.strip(), request_hash
            )
        return result


async def _replay_after_race(
    uow_factory: UnitOfWorkFactory, operator: str, key: str, request_hash: str
) -> CreateResult:
    """A lost commit race means someone else won: replay their receipt."""
    async with uow_factory() as uow:
        existing = await uow.stories.find_receipt(operator, key)
        if existing is None:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "creation raced and left nothing")
        if existing.request_hash != request_hash:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "idempotency key was used for a different request",
            )
        return await _replay(uow, existing)


async def _replay(uow: UnitOfWork, receipt: StoryCreationReceipt) -> CreateResult:
    grant = await uow.roles.get_for_world(receipt.created_world_id)
    role = grant.role.value if grant is not None else "watcher"
    character_id = grant.character_id if grant is not None else None
    return CreateResult(
        story_id=receipt.created_world_id,
        world_id=receipt.created_world_id,
        role=role,
        character_id=character_id,
        replayed=True,
    )


def _request_hash(draft: StoryDraft, expected_version: int) -> str:
    payload = draft.payload.model_dump(mode="json")
    if payload["mode"].get("adventure") is None:
        # A story without fights hashes as it did before fights existed,
        # so a receipt from then still replays.
        payload["mode"].pop("adventure", None)
    canonical = json.dumps(
        {
            "draft_id": str(draft.id),
            "expected_version": expected_version,
            "payload": payload,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _world_preset(uow: UnitOfWork, payload: DraftPayload) -> WorldPresetPayload:
    world = payload.world
    if world.preset_id is not None:
        revision = world.preset_revision or 1
        preset = await uow.presets.get_revision(world.preset_id, revision)
        parsed = preset.payload
        if not isinstance(parsed, WorldPresetPayload):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "world preset is not a world")
        return parsed
    latest = await uow.presets.get_revision(WORLD_PRESET_ID, 1)
    assert isinstance(latest.payload, WorldPresetPayload)
    return latest.payload


async def _cast_presets(
    uow: UnitOfWork, payload: DraftPayload
) -> dict[str, CharacterPresetPayload]:
    resolved: dict[str, CharacterPresetPayload] = {}
    for member in payload.cast:
        if member.preset_id is None:
            resolved[member.instance_key] = _inline_character(member)
            continue
        revision = member.preset_revision or 1
        preset = await uow.presets.get_revision(member.preset_id, revision)
        if not isinstance(preset.payload, CharacterPresetPayload):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"cast preset for {member.instance_key} is not a character",
            )
        resolved[member.instance_key] = preset.payload
    return resolved


def _inline_character(member: DraftCastMember) -> CharacterPresetPayload:
    return CharacterPresetPayload(name=member.name)


#: World config key holding the story's own map layout (see presentation).
MAP_LAYOUT = "map_layout"


def _fraction(point: tuple[int, int]) -> list[float]:
    return [point[0] / MAP_SPAN, point[1] / MAP_SPAN]


async def _copy_art(
    uow: UnitOfWork, world_id: UUID, asset_id: str, copied: dict[str, UUID]
) -> UUID | None:
    """Register a library map picture again for this world (same stored bytes),
    so the story keeps it even if the world later draws a new one. A picture
    used twice (the world's map and a place's) is registered once."""
    if asset_id in copied:
        return copied[asset_id]
    try:
        source = await uow.assets.get_asset(UUID(asset_id))
    except (DomainError, ValueError):
        return None  # the picture is gone
    art = AssetRecord(
        id=new_asset_id(),
        world_id=world_id,
        kind=AssetKind.MAP,
        content_ref=source.content_ref,
        mime=source.mime,
        width=source.width,
        height=source.height,
        style_pack_version=source.style_pack_version,
    )
    await uow.assets.add_asset(art)
    copied[asset_id] = art.id
    return art.id


async def _adopt_map(
    uow: UnitOfWork,
    world_id: UUID,
    world_map: WorldMap,
    location_ids: dict[str, UUID],
    copied: dict[str, UUID],
) -> None:
    """Give the story its world's map: the art, the pins and the drawn roads."""
    art_id = await _copy_art(uow, world_id, world_map.asset_id, copied)
    if art_id is None:
        return  # the story falls back to a schematic map
    where = {pin.key: pin.point for pin in world_map.pins}

    await uow.worlds.put_config(
        world_id,
        MAP_LAYOUT,
        {
            "asset_id": str(art_id),
            "anchors": {
                str(location_ids[key]): _fraction(point)
                for key, point in where.items()
                if key in location_ids
            },
            "roads": [
                {
                    "from": str(location_ids[road.a]),
                    "to": str(location_ids[road.b]),
                    "by": road.by,
                    "points": [_fraction(p) for p in [where[road.a], *road.points, where[road.b]]],
                }
                for road in world_map.roads
                if road.a in location_ids and road.b in location_ids
            ],
        },
    )


#: World config key holding imported portraits' frames, by character id.
PORTRAIT_FRAMES = "portrait_frames"


async def _adopt_portrait(
    uow: UnitOfWork,
    world_id: UUID,
    character_id: UUID,
    preset: CharacterPresetPayload,
    frames_by_character: dict[str, object],
) -> None:
    """Register the preset's imported picture as this character's portrait."""
    if preset.portrait_asset_id is None or preset.portrait_frames is None:
        return
    try:
        source = await uow.assets.get_asset(UUID(preset.portrait_asset_id))
    except (DomainError, ValueError):
        return  # the picture is gone: a portrait is painted as usual
    art = AssetRecord(
        id=new_asset_id(),
        world_id=world_id,
        kind=AssetKind.PORTRAIT,
        subject_id=character_id,
        content_ref=source.content_ref,
        mime=source.mime,
        width=source.width,
        height=source.height,
        style_pack_version=source.style_pack_version,
    )
    await uow.assets.add_asset(art)
    frames = preset.portrait_frames
    frames_by_character[str(character_id)] = {
        "asset_id": str(art.id),
        "portrait": as_list(frames.portrait),
        "face": as_list(frames.face),
    }
    await uow.worlds.put_config(world_id, PORTRAIT_FRAMES, frames_by_character)


#: World config key holding the story's cover: its world's own picture.
COVER = "cover"
#: Items a character brings from the library ("Carries:" in their look).
CARRIED_ITEM_KEY = "carried"


@dataclass(frozen=True)
class StoryCover:
    asset_id: UUID
    frame: Frame


def story_cover(raw: object) -> StoryCover | None:
    """The cover a story kept, from its config (unreadable: none)."""
    if not isinstance(raw, dict):
        return None
    entry = cast("dict[str, object]", raw)
    try:
        x, y, w, h = cast("list[float]", entry["frame"])
        return StoryCover(UUID(str(entry["asset_id"])), Frame(x=x, y=y, w=w, h=h))
    except (KeyError, TypeError, ValueError):
        return None


async def _adopt_cover(uow: UnitOfWork, world_id: UUID, cover: WorldCover | None) -> UUID | None:
    """Keep the world's picture with the story (its cards show it), even if
    the world later gets another; its frame goes in the story's config."""
    if cover is None:
        return None
    try:
        source = await uow.assets.get_asset(UUID(cover.asset_id))
    except (DomainError, ValueError):
        return None  # the picture is gone: the story has no cover
    art = AssetRecord(
        id=new_asset_id(),
        world_id=world_id,
        kind=AssetKind.BACKGROUND,
        content_ref=source.content_ref,
        mime=source.mime,
        width=source.width,
        height=source.height,
        style_pack_version=source.style_pack_version,
    )
    await uow.assets.add_asset(art)
    await uow.worlds.put_config(
        world_id, COVER, {"asset_id": str(art.id), "frame": as_list(cover.frame)}
    )
    return art.id


async def _adopt_place_maps(
    uow: UnitOfWork,
    world_id: UUID,
    places: list[WorldLocationPreset],
    location_ids: dict[str, UUID],
    copied: dict[str, UUID],
) -> None:
    """Give the story each place's own map: its art and its spots."""
    adopted: dict[str, object] = {}
    for place in places:
        if place.map is None or place.key not in location_ids:
            continue
        art_id = await _copy_art(uow, world_id, place.map.asset_id, copied)
        if art_id is None:
            continue
        adopted[str(location_ids[place.key])] = {
            "asset_id": str(art_id),
            "spots": [
                {"key": s.key, "name": s.name, "kind": s.kind, "point": _fraction(s.point)}
                for s in place.map.spots
            ],
        }
    if adopted:
        await uow.worlds.put_config(world_id, PLACE_MAPS, adopted)


async def _instantiate(
    uow: UnitOfWork,
    draft: StoryDraft,
    expected_draft_version: int,
    world_preset: WorldPresetPayload,
    cast_presets: dict[str, CharacterPresetPayload],
) -> CreateResult:
    payload = draft.payload
    if draft.version != expected_draft_version:
        raise DomainError(
            ErrorCode.VERSION_CONFLICT,
            f"stale draft {draft.id}: expected={expected_draft_version} actual={draft.version}",
        )
    location_ids = {place.key: new_location_id() for place in world_preset.locations}
    start_key = world_preset.starting_location_key
    if start_key not in location_ids:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "world preset has no valid start")
    for member in payload.cast:
        if member.location_key is not None and member.location_key not in location_ids:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"{member.instance_key} starts nowhere known: {member.location_key}",
            )
    world_id = new_world_id()
    title = payload.story.title or world_preset.name
    world = World(
        id=world_id,
        name=payload.world.name or world_preset.name,
        day=1,
        phase=PhaseName.DAWN,
        seed_version="story-created-v1",
    )
    await uow.worlds.add(world)
    await uow.worlds.put_config(world_id, "story_title", {"text": title})
    if payload.story.tone:
        await uow.worlds.put_config(world_id, "tone", {"text": payload.story.tone})
    travel_pairs = _validated_travel_pairs(world_preset, location_ids)
    world_map = world_preset.map

    def phases(src: str, dst: str) -> int:
        """A road drawn on the world's map takes its timed phases."""
        timed = world_map.phases_between(src, dst) if world_map else None
        return timed or 1

    def stamina(src: str, dst: str) -> int:
        """A road drawn on the map tires by its length and how it is travelled."""
        road = world_map.road_between(src, dst) if world_map else None
        return road_stamina(road.phases, road.by) if road is not None else 0

    embedded_routes: dict[str, list[Route]] = {
        key: [
            Route(
                id=new_route_id(),
                destination_location_id=location_ids[dst],
                duration_phases=phases(src, dst),
                stamina_cost=stamina(src, dst),
            )
            for (src, dst) in travel_pairs
            if src == key
        ]
        for key in location_ids
    }
    for place in world_preset.locations:
        await uow.locations.add(
            Location(
                id=location_ids[place.key],
                world_id=world_id,
                name=place.name,
                region=world_preset.name,
                capacity=12,
                routes=embedded_routes[place.key],
                discovered=True,
            )
        )
    for src, dst in travel_pairs:
        await uow.routes.add(
            TravelRoute(
                id=new_route_id(),
                world_id=world_id,
                from_location_id=location_ids[src],
                to_location_id=location_ids[dst],
                duration_phases=phases(src, dst),
                stamina_cost=stamina(src, dst),
            )
        )
    copied: dict[str, UUID] = {}
    if world_map is not None:
        await _adopt_map(uow, world_id, world_map, location_ids, copied)
    await _adopt_place_maps(uow, world_id, world_preset.locations, location_ids, copied)
    cover_id = await _adopt_cover(uow, world_id, world_preset.cover)
    runtime_characters: dict[str, UUID] = {}
    portrait_frames: dict[str, object] = {}
    for member in payload.cast:
        character_id = new_character_id()
        preset = cast_presets[member.instance_key]
        location_key = member.location_key or _preset_start(preset, start_key)
        location_id = location_ids.get(location_key, location_ids[start_key])
        await uow.characters.add_identity(character_id, world_id, member.name)
        await uow.characters.add_card(
            CharacterCard(
                id=new_card_id(),
                character_id=character_id,
                name=member.name,
                appearance=preset.appearance or "",
                personality=preset.personality or "",
                background=preset.background or "",
                pronouns=preset.pronouns or "",
                version=1,
            )
        )
        await uow.characters.add_state(
            Character(
                id=character_id,
                world_id=world_id,
                name=member.name,
                card_version=1,
                life_status=LifeStatus.ALIVE,
                location_id=location_id,
                stamina=80,
                mana=50,
                conditions=[],
            )
        )
        # What the studio says they carry, they hold from the first beat.
        for item_name in carried_items(preset.appearance):
            await uow.inventory.add_item(
                ItemInstance(
                    id=new_item_instance_id(),
                    world_id=world_id,
                    item_key=CARRIED_ITEM_KEY,
                    owner_id=character_id,
                    name=item_name,
                )
            )
        runtime_characters[member.instance_key] = character_id
        # A picture the player brought is this character's portrait: the
        # job below then binds it instead of painting one.
        await _adopt_portrait(uow, world_id, character_id, preset, portrait_frames)
        await queue_image(uow, world_id, AssetKind.PORTRAIT, character_id)
    await uow.versions.ensure(world_id, world_id, "world")
    for location_id in location_ids.values():
        await uow.versions.ensure(location_id, world_id, "location")
    for character_id in runtime_characters.values():
        await uow.versions.ensure(character_id, world_id, "character")
    run_id = uuid4()
    command_id = uuid4()
    event_id = uuid4()
    await uow.phases.create_run(
        PhaseRun(id=run_id, world_id=world_id, absolute_index=0, state=PhaseRunState.COMPLETED)
    )
    await uow.commands.add(
        command_id=command_id,
        world_id=world_id,
        key=f"story:{world_id.hex}",
        actor_role="system",
        command_type="create_story",
        expected_versions={},
        payload={"world_id": str(world_id), "draft_id": str(draft.id)},
        input_hash=_request_hash(draft, expected_draft_version),
    )
    await uow.events.append_event(
        WorldEvent(
            id=event_id,
            world_id=world_id,
            sequence=1,
            event_type=EventType.WORLD_SEEDED,
            absolute_index=0,
            phase_run_id=run_id,
            source_command_id=command_id,
            summary={"seed_version": "story-created-v1", "title": title},
        )
    )
    await uow.commands.set_result(command_id, event_id)
    role = UserRole(payload.mode.role)
    controlled: UUID | None = None
    if role == UserRole.PLAYER:
        assert payload.mode.controlled_cast_key is not None
        controlled = runtime_characters[payload.mode.controlled_cast_key]
    await uow.roles.set_grant(
        RoleGrant(
            id=new_role_grant_id(),
            world_id=world_id,
            role=role,
            character_id=controlled,
            granted_absolute=0,
        )
    )
    adventure = payload.mode.adventure
    if adventure is not None and controlled is not None:
        # A story with fights: the hero's 5e sheet joins in the same
        # transaction, so a failure leaves no story half made.
        hero = next(m for m in payload.cast if m.instance_key == payload.mode.controlled_cast_key)
        await uow.party.add(
            PartyMember(
                id=new_party_member_id(),
                world_id=world_id,
                name=hero.name,
                name_key=party_name_key(hero.name),
                character_id=controlled,
                focus_slot=focus_for_seat(0),
                sheet=auto_sheet(
                    hero.name, adventure.race, adventure.character_class, 1, story_dnd_tables()
                ),
            )
        )
    setup_payload = _snapshot_payload(
        payload, world_preset, cast_presets, runtime_characters, location_ids, role
    )
    await uow.stories.put_setup(
        StoryInitialSetup(
            world_id=world_id,
            payload=setup_payload,
            content_hash=_hash(setup_payload),
            created_at=utcnow(),
            provenance=SetupProvenance.CREATED,
        )
    )
    await uow.stories.put_catalog(
        StoryCatalogEntry(
            world_id=world_id, title=title, created_at=utcnow(), cover_asset_id=cover_id
        )
    )
    await uow.stories.save_draft(
        draft.model_copy(update={"created_world_id": world_id, "updated_at": utcnow()}),
        expected_draft_version,
    )
    return CreateResult(
        story_id=world_id,
        world_id=world_id,
        role=role.value,
        character_id=controlled,
        replayed=False,
    )


def _validated_travel_pairs(
    world_preset: WorldPresetPayload,
    location_ids: dict[str, UUID],
) -> list[tuple[str, str]]:
    """Validate preset travel pairs; fail before any write when invalid."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in world_preset.travel:
        if len(pair) != 2:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, f"travel pair must name two places: {pair!r}"
            )
        src, dst = pair[0], pair[1]
        if src not in location_ids or dst not in location_ids:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, f"travel endpoint unknown: {src!r} -> {dst!r}"
            )
        if src == dst:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"travel leg cannot loop: {src!r}")
        if (src, dst) in seen:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, f"duplicate travel leg: {src!r} -> {dst!r}"
            )
        seen.add((src, dst))
        pairs.append((src, dst))
    return pairs


def _preset_start(preset: CharacterPresetPayload, fallback: str) -> str:
    return preset.starting_location_key or fallback


def _snapshot_payload(
    payload: DraftPayload,
    world_preset: WorldPresetPayload,
    cast_presets: dict[str, CharacterPresetPayload],
    runtime_characters: dict[str, UUID],
    location_ids: dict[str, UUID],
    role: UserRole,
) -> dict[str, Any]:
    inner = payload
    return {
        "schema_version": 1,
        "provenance": "created",
        "world": {
            "preset_revision": inner.world.preset_revision or 1,
            "name": inner.world.name or world_preset.name,
            "starting_location_key": world_preset.starting_location_key,
            "locations": {key: str(location_id) for key, location_id in location_ids.items()},
            "resolved": world_preset.model_dump(mode="json"),
        },
        "cast": [
            {
                "instance_key": member.instance_key,
                "name": member.name,
                "location_key": member.location_key,
                "runtime_character_id": str(runtime_characters[member.instance_key]),
                "preset_revision": member.preset_revision or 1,
                "resolved": cast_presets[member.instance_key].model_dump(mode="json"),
            }
            for member in inner.cast
        ],
        "mode": {
            "role": role.value,
            "controlled_cast_key": inner.mode.controlled_cast_key,
            "controlled_character_id": (
                str(runtime_characters[inner.mode.controlled_cast_key])
                if role == UserRole.PLAYER and inner.mode.controlled_cast_key is not None
                else None
            ),
            **(
                {"adventure": inner.mode.adventure.model_dump(mode="json")}
                if inner.mode.adventure is not None
                else {}
            ),
        },
        "story": inner.story.model_dump(mode="json"),
        "art": inner.ai.model_dump(mode="json"),
    }


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def register_curated_art(
    uow_factory: UnitOfWorkFactory, assets_root: Path, world_id: UUID
) -> int:
    """Name-based starter registration after the story commit; never rolls back."""
    from worldsim.application.assets import ensure_starter

    registered = await ensure_starter(uow_factory, world_id, assets_root)
    return len(registered)
