"""Built-in Library presets with stable identities (owned by MAINMENU-A03).

The 0030 migration inserts the same rows for fresh upgrades; this service
keeps older databases converging and is safe to call repeatedly: existing
IDs are never rewritten.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.presets import (
    CharacterPresetPayload,
    Preset,
    PresetKind,
    PresetPayload,
    PresetRevision,
    StylePackPayload,
    TemplatePresetPayload,
    WorldLocationPreset,
    WorldPresetPayload,
    canonical_payload_hash,
)
from worldsim.domain.time import utcnow

WORLD_PRESET_ID = UUID("20000000-0000-4000-8000-000000000001")
WREN_PRESET_ID = UUID("20000000-0000-4000-8000-000000000101")
ASH_PRESET_ID = UUID("20000000-0000-4000-8000-000000000102")
STYLE_PRESET_ID = UUID("20000000-0000-4000-8000-000000000201")
TEMPLATE_PRESET_ID = UUID("20000000-0000-4000-8000-000000000301")


def _hash(payload: PresetPayload) -> str:
    """Delegate to the canonical domain hash; kept as the call-site name."""
    return canonical_payload_hash(payload)


def builtin_definitions() -> list[tuple[UUID, PresetKind, str, PresetPayload]]:
    world = WorldPresetPayload(
        name="Ember Vale",
        description="A sheltered vale of hearths, markets, and old roads.",
        lore="The vale keeps its stories close.",
        locations=[
            WorldLocationPreset(key="hearth", name="Hearth"),
            WorldLocationPreset(key="market", name="Market"),
        ],
        travel=[],
        starting_location_key="hearth",
        default_cast=["wren", "ash"],
        style_pack_id="anime-saga-v1",
    )
    wren = CharacterPresetPayload(
        name="Wren",
        appearance="Quick eyes and a traveler's coat.",
        personality="Curious, kind, asks what if.",
        background="Road-raised and story-fed.",
        portrait_asset_id=None,
        tags=["Human", "Explorer", "Player-ready"],
        starting_location_key="hearth",
    )
    ash = CharacterPresetPayload(
        name="Ash",
        appearance="Steady stance, weather-worn cloak.",
        personality="Patient, dry-witted, dependable.",
        background="Market ward born and bred.",
        portrait_asset_id=None,
        tags=["Human", "Wanderer", "Player-ready"],
        starting_location_key="market",
    )
    style = StylePackPayload(
        display_name="Anime Saga",
        style_id="anime-saga-v1",
        guidance="Warm anime-fantasy key art with expressive portraits.",
    )
    template = TemplatePresetPayload(
        display_name="Ember Vale opening",
        world_preset_id=str(WORLD_PRESET_ID),
        world_preset_revision=1,
        cast_preset_ids=[str(WREN_PRESET_ID), str(ASH_PRESET_ID)],
        tone="hopeful mystery",
        pacing="measured",
    )
    return [
        (WORLD_PRESET_ID, PresetKind.WORLD, "Ember Vale", world),
        (WREN_PRESET_ID, PresetKind.CHARACTER, "Wren", wren),
        (ASH_PRESET_ID, PresetKind.CHARACTER, "Ash", ash),
        (STYLE_PRESET_ID, PresetKind.STYLE_PACK, "Anime Saga", style),
        (TEMPLATE_PRESET_ID, PresetKind.TEMPLATE, "Ember Vale opening", template),
    ]


def builtin_revision_updates() -> list[tuple[UUID, int, PresetPayload]]:
    """Corrected follow-up revisions for built-ins (never rewrite rev 1).

    World rev 2 carries the intended Hearth <-> Market directed legs;
    template rev 2 pins world rev 2. Character and style presets are
    unchanged. Hashes use the canonical domain algorithm.
    """
    world = WorldPresetPayload(
        name="Ember Vale",
        description="A sheltered vale of hearths, markets, and old roads.",
        lore="The vale keeps its stories close.",
        locations=[
            WorldLocationPreset(key="hearth", name="Hearth"),
            WorldLocationPreset(key="market", name="Market"),
        ],
        travel=[["hearth", "market"], ["market", "hearth"]],
        starting_location_key="hearth",
        default_cast=["wren", "ash"],
        style_pack_id="anime-saga-v1",
    )
    template = TemplatePresetPayload(
        display_name="Ember Vale opening",
        world_preset_id=str(WORLD_PRESET_ID),
        world_preset_revision=2,
        cast_preset_ids=[str(WREN_PRESET_ID), str(ASH_PRESET_ID)],
        tone="hopeful mystery",
        pacing="measured",
    )
    return [(WORLD_PRESET_ID, 2, world), (TEMPLATE_PRESET_ID, 2, template)]


async def _ensure_revision(
    uow: UnitOfWork, preset_id: UUID, revision: int, payload: PresetPayload
) -> bool:
    """Insert one revision when missing; never rewrite. Returns True if added."""
    try:
        await uow.presets.get_revision(preset_id, revision)
        return False
    except DomainError as exc:
        if exc.code != ErrorCode.NOT_FOUND:
            raise
    await uow.presets.add_revision(
        PresetRevision(
            preset_id=preset_id,
            revision=revision,
            schema_version=1,
            payload=payload,
            content_hash=canonical_payload_hash(payload),
            created_at=utcnow(),
        )
    )
    return True


async def ensure_builtin_presets(uow: UnitOfWork) -> int:
    """Converge missing built-ins and corrected rev 2 rows; count added.

    Existing rows are never rewritten. Preset rows inserted fresh start at
    current_revision 2 with both revisions; current_revision on pre-existing
    readonly rows is migration-managed (0033), not bumped here.
    """
    added = 0
    now = utcnow()
    for preset_id, kind, name, payload in builtin_definitions():
        if await uow.presets.find_preset(preset_id) is not None:
            continue
        await uow.presets.add_preset(
            Preset(
                id=preset_id,
                kind=kind,
                name=name,
                builtin=True,
                readonly=True,
                current_revision=2,
                created_at=now,
            )
        )
        await uow.presets.add_revision(
            PresetRevision(
                preset_id=preset_id,
                revision=1,
                schema_version=1,
                payload=payload,
                content_hash=_hash(payload),
                created_at=now,
            )
        )
        added += 1
    for preset_id, revision, payload in builtin_revision_updates():
        if await _ensure_revision(uow, preset_id, revision, payload):
            added += 1
    return added
