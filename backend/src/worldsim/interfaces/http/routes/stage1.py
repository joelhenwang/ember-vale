"""Stage 1 perspective reads and player commands (owned by S1-API-001).

Two roles: watcher (omniscient reads plus model audit) and player
(scoped to one character via X-Worldsim-Character). Anything outside
the player's own participation is 403; model runs and manifests never
leave the watcher boundary. Command stability comes from the
orchestrator's idempotent keys: repeats return stored reports.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import TypeAdapter

from worldsim.application.capabilities import Capability, parse_role, require_capability
from worldsim.application.commands.inventory import purse_of
from worldsim.application.commands.party import (
    begin_adventure,
    calling_state,
    change_calling,
    choose_level_option,
    create_character,
    link_member,
)
from worldsim.application.orchestration.stage1 import Stage1Orchestrator, item_label, shop_goods
from worldsim.application.queries.suggestions import suggestions_for
from worldsim.application.stories.guards import require_unarchived
from worldsim.domain.commands import ActionIntent
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import derive_attempt_id
from worldsim.domain.party import PartyMember, fight_keys, foes_on
from worldsim.domain.rules.coins import COINS_KEY
from worldsim.domain.rules.dnd import DataTables, armor_ac, strip_combat_tags, xp_for_level
from worldsim.domain.rules.dnd.data import entry, table
from worldsim.domain.rules.dnd.progress import class_slots, long_rest, slots_left
from worldsim.domain.rules.dnd.sheets import Sheet
from worldsim.domain.rules.shop import for_sale, sell_price, seller_kind
from worldsim.domain.scenes import Intent, Reaction
from worldsim.domain.time import absolute_index
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.beats import run_beat
from worldsim.interfaces.http.routes.roles import effective_role
from worldsim.interfaces.http.state import dnd_tables

router = APIRouter(tags=["stage1"])

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)


def _named(rows: dict[str, Any], keys: list[str]) -> list[str]:
    return [str(entry(rows, key).get("name", key)) for key in keys]


def _spell_options(tables: DataTables, keys: list[str]) -> list[api.SpellOption]:
    spells = table(tables, "spells")
    rows = [
        api.SpellOption(
            key=key,
            name=str(entry(spells, key).get("name", key)),
            level=int(entry(spells, key).get("level", 0) or 0),
        )
        for key in keys
    ]
    return sorted(rows, key=lambda row: (row.level, row.name))


def _choices(tables: DataTables, sheet: Sheet) -> list[api.LevelChoiceView]:
    views: list[api.LevelChoiceView] = []
    for choice in sheet.choices:
        picked = _spell_options(tables, choice.picked)
        # Swaps of the picked spells' own levels (choices kept before that
        # rule also listed cantrips for a first-level spell).
        levels = {spell.level for spell in picked}
        options = [o for o in _spell_options(tables, choice.options) if o.level in levels]
        views.append(
            api.LevelChoiceView(
                id=choice.id, kind=choice.kind, level=choice.level, picked=picked, options=options
            )
        )
    return views


def _party_view(
    member: PartyMember,
    tables: DataTables | None = None,
    day: int | None = None,
    changeable: bool = False,
) -> api.PartyMemberView:
    """Project one roster row; sheets are shared party knowledge. ``day`` is
    the story day the free slots are counted for (None: as stored);
    ``changeable``: a companion whose calling may still change."""
    tables = tables if tables is not None else dnd_tables()
    # As the sheet woke today: a new story day was the night's long rest.
    sheet = long_rest(member.sheet, day)
    hit_points = sheet.hp
    return api.PartyMemberView(
        id=member.id,
        world_id=member.world_id,
        name=member.name,
        level=sheet.level,
        character_class=sheet.character_class,
        hp_current=hit_points.current if hit_points else None,
        hp_max=hit_points.max if hit_points else None,
        conditions=list(sheet.conditions),
        character_id=member.character_id,
        version=member.version,
        race=sheet.race,
        armor_class=armor_ac(tables, sheet),
        weapons=_named(table(tables, "weapons"), sheet.weapons),
        spells=_named(table(tables, "spells"), sheet.spells),
        spell_slots=class_slots(tables, sheet),
        spell_slots_left=slots_left(tables, sheet, day),
        xp=sheet.xp,
        xp_level_start=xp_for_level(sheet.level),
        xp_next_level=None if sheet.level >= 20 else xp_for_level(sheet.level + 1),
        abilities=dict(sheet.stats),
        choices=_choices(tables, sheet),
        calling_changeable=changeable,
    )


async def _foes(uow: Any, world_id: UUID) -> tuple[list[api.FoeView], int | None]:
    """The latest fight's foes with live hit points, while it is on: rolled
    within the last turns and someone still standing."""
    fight = await uow.events.latest_fight(world_id)
    if fight is None:
        return [], None
    world = await uow.worlds.get(world_id)
    foes = foes_on(
        fight.absolute_index,
        absolute_index(world.day, world.phase),
        fight_keys(fight.summary),
        await uow.monsters.list_for_world(world_id),
    )
    return [
        api.FoeView(
            key=foe.name_key,
            name=foe.name,
            hp_current=foe.hp_current,
            hp_max=foe.hp_max,
            armor_class=foe.ac,
        )
        for foe in foes
    ], fight.absolute_index


async def _perspective(request: Request, world_id: UUID | None = None) -> tuple[str, UUID | None]:
    """Header perspective for reads; grant-aware role for mutating routes.

    World-scoped callers must follow with a capability check; this helper
    no longer rejects Director/Deity up front (both hold ADVANCE).
    """
    if world_id is None:
        role = request.headers.get("x-worldsim-role", "watcher").lower()
        if role not in ("watcher", "player", "director", "deity"):
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown role: {role}")
        raw_character = request.headers.get("x-worldsim-character")
        if role == "player":
            if not raw_character:
                raise DomainError(
                    ErrorCode.FORBIDDEN, "player perspective needs X-Worldsim-Character"
                )
            try:
                return role, UUID(raw_character)
            except ValueError as exc:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "bad character id") from exc
        return role, None
    role, viewer = await effective_role(request, world_id)
    if role not in ("watcher", "player", "director", "deity", "system"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown role: {role}")
    if role == "player" and viewer is None:
        raise DomainError(ErrorCode.FORBIDDEN, "player perspective needs a bound character")
    return role, viewer


def _stage1(request: Request) -> Stage1Orchestrator:
    state = request.app.state.app_state
    return state.stage1()


def _intent_view(intent: Intent, viewer: UUID | None) -> api.IntentView:
    detail: dict[str, object] | None = None
    if viewer is None or intent.author_character_id == viewer:
        detail = intent.action.model_dump(mode="json")
    return api.IntentView(
        id=intent.id,
        author_character_id=intent.author_character_id,
        family=intent.action.family.value,
        detail=detail,
    )


def _reaction_view(reaction: Reaction, viewer: UUID | None) -> api.ReactionView:
    detail: dict[str, object] | None = None
    if viewer is None or reaction.reactor_character_id == viewer:
        detail = reaction.action.model_dump(mode="json")
    return api.ReactionView(
        id=reaction.id,
        reactor_character_id=reaction.reactor_character_id,
        family=reaction.action.family.value,
        detail=detail,
    )


async def _scene_detail(request: Request, scene_id: UUID, viewer: UUID | None) -> api.SceneDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        scene = await uow.scenes.get_scene(scene_id)
        if viewer is not None and all(p.character_id != viewer for p in scene.participants):
            raise DomainError(ErrorCode.FORBIDDEN, "scene outside player participation")
        intents = [await uow.scenes.get_intent(i) for i in scene.intent_ids]
        attempts = [await uow.scenes.get_attempt(derive_attempt_id(i)) for i in scene.intent_ids]
        reactions = await uow.scenes.reactions_for_scene(scene_id)
        try:
            resolution = await uow.scenes.get_resolution(scene_id)
            resolution_view: api.ResolutionView | None = api.ResolutionView(
                outcome=resolution.outcome.value,
                resolver=resolution.resolver.value,
                rationale=resolution.rationale,
            )
        except DomainError as exc:
            if exc.code is not ErrorCode.NOT_FOUND:
                raise
            resolution_view = None
    return api.SceneDetail(
        id=scene.id,
        world_id=scene.world_id,
        phase_run_id=scene.phase_run_id,
        status=scene.status.value,
        beat_budget=scene.beat_budget,
        event_id=scene.event_id,
        participants=[
            api.ParticipantView(character_id=p.character_id, role=p.role.value)
            for p in scene.participants
        ],
        intents=[_intent_view(i, viewer) for i in intents],
        attempts=[
            api.AttemptView(
                id=a.id,
                actor_character_id=a.actor_character_id,
                observable_summary=a.observable_summary,
                status=a.status.value,
            )
            for a in attempts
        ],
        reactions=[_reaction_view(r, viewer) for r in reactions],
        resolution=resolution_view,
    )


@router.get("/stage1/characters", response_model=list[api.CharacterSummary])
async def list_characters(request: Request, world_id: UUID) -> list[api.CharacterSummary]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        characters = await uow.characters.list_for_world(world_id)
    return [
        api.CharacterSummary(
            id=c.id, name=c.name, life_status=c.life_status.value, location_id=c.location_id
        )
        for c in characters
    ]


@router.get("/stage1/characters/{character_id}", response_model=api.CharacterDetail)
async def get_character(character_id: UUID, request: Request) -> api.CharacterDetail:
    _role, viewer = await _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        character = await uow.characters.get(character_id)
        card: dict[str, object] | None = None
        detail_state: dict[str, object] | None = None
        if viewer is None or viewer == character_id:
            card_row = await uow.characters.get_card(character_id, character.card_version)
            card = {
                "name": card_row.name,
                "appearance": card_row.appearance,
                "personality": card_row.personality,
                "background": card_row.background,
                "pronouns": card_row.pronouns,
                "version": card_row.version,
            }
            detail_state = {
                "stamina": character.stamina,
                "mana": character.mana,
                "conditions": list(character.conditions),
                "card_version": character.card_version,
                "version": character.version,
            }
    return api.CharacterDetail(
        id=character.id,
        name=character.name,
        life_status=character.life_status.value,
        location_id=character.location_id,
        card=card,
        state=detail_state,
    )


@router.get("/stage1/suggestions", response_model=list[api.SuggestionView])
async def character_suggestions(character_id: UUID, request: Request) -> list[api.SuggestionView]:
    """Validated contextual actions for one character; players read only themselves."""
    _role, viewer = await _perspective(request)
    if viewer is not None and viewer != character_id:
        raise DomainError(ErrorCode.FORBIDDEN, "players read only their own suggestions")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        return await suggestions_for(uow, character_id)


@router.get("/stage1/scenes", response_model=list[api.SceneSummary])
async def list_scenes(
    request: Request, phase_run_id: UUID, limit: int = 50
) -> list[api.SceneSummary]:
    _role, viewer = await _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        scenes = await uow.scenes.list_for_run(phase_run_id, limit=max(1, min(limit, 200)))
    summaries: list[api.SceneSummary] = []
    for scene in scenes:
        if viewer is not None and all(p.character_id != viewer for p in scene.participants):
            continue
        summaries.append(
            api.SceneSummary(
                id=scene.id,
                status=scene.status.value,
                event_id=scene.event_id,
                participant_ids=[p.character_id for p in scene.participants],
            )
        )
    return summaries


@router.get("/stage1/scenes/{scene_id}", response_model=api.SceneDetail)
async def get_scene(scene_id: UUID, request: Request) -> api.SceneDetail:
    _role, viewer = await _perspective(request)
    return await _scene_detail(request, scene_id, viewer)


@router.get("/stage1/scenes/{scene_id}/narration", response_model=list[api.BeatView])
async def get_narration(scene_id: UUID, request: Request) -> list[api.BeatView]:
    _role, viewer = await _perspective(request)
    detail = await _scene_detail(request, scene_id, viewer)
    if detail.event_id is None:
        return []
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        beats = await uow.scenes.narrations_for_event(detail.event_id)
    # Combat tags are what the dice rolled from, not prose: never shown.
    return [
        api.BeatView(
            id=b.id,
            speaker_id=b.speaker_id,
            kind=b.kind.value,
            text=text,
            source_event_id=b.source_event_id,
            cited_fact_keys=list(b.cited_fact_keys),
        )
        for b in beats
        if (text := strip_combat_tags(b.text)) or not b.text
    ]


@router.get("/stage1/model-runs", response_model=list[api.ModelRunView])
async def list_model_runs(request: Request, phase_run_id: UUID) -> list[api.ModelRunView]:
    role, _viewer = await _perspective(request)
    if role != "watcher":
        raise DomainError(ErrorCode.FORBIDDEN, "model runs are watcher-only")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        calls = await uow.traces.list_for_phase_run(phase_run_id)
        views: list[api.ModelRunView] = []
        for call in calls:
            try:
                manifest = await uow.traces.get_manifest(call.id)
                manifest_id: UUID | None = manifest.id
                rendered: str | None = manifest.rendered_hash
                budgets: dict[str, int] = dict(manifest.budgets)
            except DomainError:
                manifest_id, rendered, budgets = None, None, {}
            attempts = await uow.traces.get_call_attempts(call.id)
            views.append(
                api.ModelRunView(
                    call_id=call.id,
                    role=call.role,
                    profile=f"{call.profile_name}@{call.profile_version}",
                    status=call.status.value,
                    actor_id=call.actor_id,
                    task_run_id=call.task_run_id,
                    manifest_id=manifest_id,
                    rendered_hash=rendered,
                    prompt_tokens=call.prompt_tokens,
                    completion_tokens=call.completion_tokens,
                    latency_ms=call.latency_ms,
                    error_code=call.error_code,
                    finish_reason=call.finish_reason,
                    reasoning_tokens=call.reasoning_tokens,
                    content_type=call.content_type,
                    content_length=call.content_length,
                    reasoning_only=call.reasoning_only,
                    max_tokens=call.max_tokens,
                    pin_profile_id=call.pin_profile_id,
                    pin_profile_revision=call.pin_profile_revision,
                    budgets=budgets,
                    attempts=attempts,
                )
            )
    return views


@router.post("/stage1/advance", response_model=api.Stage1AdvanceResponse)
async def advance(
    body: api.Stage1AdvanceRequest, request: Request, response: Response
) -> api.Stage1AdvanceResponse:
    role, viewer = await _perspective(request, body.world_id)
    require_capability(parse_role(role), Capability.ADVANCE)
    if role == "watcher" and body.player_intents:
        raise DomainError(
            ErrorCode.FORBIDDEN,
            "watch mode advances the world but files no attempts; "
            "switch to Player or queue a direction",
        )
    if role in ("director", "deity") and body.player_intents:
        raise DomainError(
            ErrorCode.FORBIDDEN,
            "directed attempts go through the intervention queue, not advance",
        )
    player_intents: dict[UUID, ActionIntent] = {}
    for raw_actor, raw_action in body.player_intents.items():
        try:
            actor = UUID(raw_actor)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "bad actor id") from exc
        if viewer is not None and actor != viewer:
            raise DomainError(ErrorCode.FORBIDDEN, "players substitute only themselves")
        player_intents[actor] = _ACTION_ADAPTER.validate_python(raw_action)

    report, slot_claim_ms, execution_ms = await run_beat(
        request.app.state.app_state,
        body.world_id,
        body.absolute_index,
        player_intents,
        submitter_id=viewer,
    )
    # Baseline timing only: slot-claim is the execution-slot wait (not run
    # admission), execution is the admitted beat. Headers keep the response
    # contract unchanged.
    response.headers["X-Worldsim-Slot-Claim-Ms"] = str(slot_claim_ms)
    response.headers["X-Worldsim-Execution-Ms"] = str(execution_ms)
    # Per-stage wall time of the beat (probe, director, decide, react,
    # resolve, narrate, ...), compact JSON; empty on a duplicate replay.
    response.headers["X-Worldsim-Phase-Timings"] = json.dumps(
        report.timings_ms, separators=(",", ":"), sort_keys=True
    )
    return api.Stage1AdvanceResponse(
        run_id=report.run_id,
        world_id=report.world_id,
        absolute_index=report.absolute_index,
        snapshot_id=report.snapshot_id,
        scenes=[
            api.Stage1SceneOutcome(
                scene_id=s.scene_id,
                event_id=s.event_id,
                resolution_outcome=s.resolution_outcome,
                narration=s.narration,
            )
            for s in report.scenes
        ],
        duplicate=report.duplicate,
        quiet=report.quiet,
    )


@router.post("/stage1/pause", response_model=dict[str, str])
async def pause(body: api.RunIdRequest, request: Request) -> dict[str, str]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world_id = (await uow.phases.get_run(body.run_id)).world_id
        await require_unarchived(uow, world_id)
    role, _viewer = await _perspective(request, world_id)
    require_capability(parse_role(role), Capability.ADVANCE)
    await _stage1(request).pause_phase(body.run_id)
    return {"run_id": str(body.run_id), "state": "paused"}


@router.get("/simulation/status", response_model=api.SimulationStatus)
async def simulation_status(world_id: UUID, request: Request) -> api.SimulationStatus:
    """Reconcile open and latest runs without starting work."""
    role, _viewer = await _perspective(request, world_id)
    require_capability(parse_role(role), Capability.ADVANCE)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world = await uow.worlds.get(world_id)
        open_run = await uow.phases.find_open_run(world_id)
        latest = await uow.phases.latest_run(world_id)
    return api.SimulationStatus(
        world_id=world_id,
        absolute_index=absolute_index(world.day, world.phase),
        open_run_id=open_run.id if open_run is not None else None,
        open_run_index=open_run.absolute_index if open_run is not None else None,
        open_run_state=open_run.state.value if open_run is not None else None,
        latest_run_id=latest.id if latest is not None else None,
        latest_run_state=latest.state.value if latest is not None else None,
    )


@router.post("/stage1/resume", response_model=dict[str, str])
async def resume(body: api.RunIdRequest, request: Request) -> dict[str, str]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        world_id = (await uow.phases.get_run(body.run_id)).world_id
        await require_unarchived(uow, world_id)
    role, _viewer = await _perspective(request, world_id)
    require_capability(parse_role(role), Capability.ADVANCE)
    await _stage1(request).resume_phase(body.run_id)
    return {"run_id": str(body.run_id), "state": "resumed"}


@router.post("/stage1/party/begin", response_model=api.PartyMemberView)
async def begin_party_member(body: api.PartyBeginRequest, request: Request) -> api.PartyMemberView:
    """Seat the player's adventurer (explicit stats or the auto build)."""
    role, _viewer = await _perspective(request, body.world_id)
    require_capability(parse_role(role), Capability.CREATE_CHARACTER)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await require_unarchived(uow, body.world_id)
        member = await begin_adventure(
            uow,
            dnd_tables(),
            body.world_id,
            body.name,
            body.race,
            body.character_class,
            body.level,
            body.stats,
            character_id=body.character_id,
        )
    return _party_view(member)


@router.post("/stage1/characters", response_model=api.CharacterSummary)
async def create_character_view(
    body: api.CharacterCreateRequest, request: Request
) -> api.CharacterSummary:
    """Create a simulation character with its identity card."""
    role, _viewer = await _perspective(request, body.world_id)
    require_capability(parse_role(role), Capability.CREATE_CHARACTER)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await require_unarchived(uow, body.world_id)
        character = await create_character(
            uow,
            body.world_id,
            body.name,
            body.location_id,
            appearance=body.appearance,
            personality=body.personality,
            background=body.background,
            pronouns=body.pronouns,
        )
    return api.CharacterSummary(
        id=character.id,
        name=character.name,
        life_status=character.life_status.value,
        location_id=character.location_id,
    )


@router.post("/stage1/party/{member_id}/link", response_model=api.PartyMemberView)
async def link_party_member(
    member_id: UUID, body: api.PartyLinkRequest, request: Request
) -> api.PartyMemberView:
    """Bind an existing roster row to a real character, version-checked."""
    role, _viewer = await _perspective(request, body.world_id)
    require_capability(parse_role(role), Capability.CREATE_CHARACTER)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await require_unarchived(uow, body.world_id)
        member = await link_member(
            uow, body.world_id, member_id, body.character_id, body.expected_version
        )
    return _party_view(member)


@router.post("/stage1/party/{member_id}/choices", response_model=api.PartyMemberView)
async def choose_party_level_option(
    member_id: UUID, body: api.LevelChoiceRequest, request: Request
) -> api.PartyMemberView:
    """Make a level-up choice: the hero's own player (or a Director or God)."""
    role, viewer = await _perspective(request, body.world_id)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await require_unarchived(uow, body.world_id)
        member = await uow.party.get(member_id)
        if role == "player" and (viewer is None or member.character_id != viewer):
            raise DomainError(ErrorCode.FORBIDDEN, "only this hero's player chooses")
        if role not in ("player", "director", "deity"):
            raise DomainError(ErrorCode.FORBIDDEN, "watchers do not choose for heroes")
        member = await choose_level_option(
            uow,
            body.world_id,
            member_id,
            body.choice_id,
            body.expected_version,
            abilities=body.abilities,
            spells=body.spells,
        )
        today = (await uow.worlds.get(body.world_id)).day
    return _party_view(member, dnd_tables(), today)


@router.post("/stage1/party/{member_id}/calling", response_model=api.PartyMemberView)
async def change_party_calling(
    member_id: UUID, body: api.PartyCallingRequest, request: Request
) -> api.PartyMemberView:
    """Another people and calling for a companion who has not fought yet: the
    hero's own player (or a Director or God)."""
    role, viewer = await _perspective(request, body.world_id)
    if role not in ("player", "director", "deity"):
        raise DomainError(ErrorCode.FORBIDDEN, "watchers do not change the party")
    state = request.app.state.app_state
    tables = dnd_tables()
    async with state.uow_factory()() as uow:
        await require_unarchived(uow, body.world_id)
        if role == "player":
            grant = await uow.roles.get_for_world(body.world_id)
            if viewer is None or grant is None or grant.character_id != viewer:
                raise DomainError(ErrorCode.FORBIDDEN, "only the hero's player changes callings")
        member = await change_calling(
            uow,
            tables,
            body.world_id,
            member_id,
            body.race,
            body.character_class,
            body.expected_version,
        )
        today = (await uow.worlds.get(body.world_id)).day
        changeable = (await calling_state(uow, body.world_id)).changeable(member)
    return _party_view(member, tables, today, changeable)


@router.get("/stage1/shop", response_model=api.ShopResponse)
async def shop(world_id: UUID, request: Request) -> api.ShopResponse:
    """What is for sale where the played character stands, in a combat
    story, and their purse (shops-001). Empty for watchers."""
    _role, viewer = await _perspective(request, world_id)
    state = request.app.state.app_state
    if viewer is None:
        return api.ShopResponse(world_id=world_id)
    async with state.uow_factory()() as uow:
        if not await uow.party.list_for_world(world_id):
            return api.ShopResponse(world_id=world_id)
        character = await uow.characters.get(viewer)
        place = await uow.locations.get(character.location_id)
        purse = await purse_of(uow, world_id, viewer)
        held = await uow.inventory.list_for_owner(world_id, viewer)
    goods = for_sale(place.name, shop_goods())
    kind = seller_kind(place.name)
    weapons = table(dnd_tables(), "weapons")
    buys = [
        api.ShopSaleView(item_id=item.id, name=item_label(item), price=price)
        for item in held
        if item.item_key != COINS_KEY
        and (price := sell_price(item.item_key, kind, shop_goods(), weapons)) > 0
    ]
    return api.ShopResponse(
        world_id=world_id,
        place=place.name if goods else None,
        buys=buys if goods else [],
        goods=[
            api.ShopGoodView(
                key=g.key, name=g.name, price=g.price, description=g.description, keep=g.keep
            )
            for g in goods
        ],
        purse=purse,
    )


@router.get("/stage1/party", response_model=api.PartyRosterResponse)
async def party_roster(world_id: UUID, request: Request) -> api.PartyRosterResponse:
    """Party sheets are shared party knowledge: full roster for both roles."""
    _role, _viewer = await _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        members = await uow.party.list_for_world(world_id)
        foes, fought = await _foes(uow, world_id) if members else ([], None)
        today = (await uow.worlds.get(world_id)).day if members else None
        callings = await calling_state(uow, world_id) if members else None
    tables = dnd_tables()
    return api.PartyRosterResponse(
        world_id=world_id,
        members=[
            _party_view(member, tables, today, callings is not None and callings.changeable(member))
            for member in members
        ],
        foes=foes,
        fight_index=fought,
    )
