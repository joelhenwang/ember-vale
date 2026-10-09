"""Three-phase autonomous orchestration (owned by S1-ORCH-001).

One phase runs seal -> decide -> assemble -> react -> resolve -> commit
-> narrate. Character decisions run concurrently after the snapshot
seal; every later stage is a barrier. Restarts are safe by
construction: deterministic run, snapshot, task, intent, attempt,
reaction, resolution, and scene IDs plus idempotent command keys mean
re-running a phase replays stored results instead of doubling canon.

Task-run rows are deliberately not written: S1 character work is a
synchronous in-process unit, and recovery flows through idempotent
commits, not lease healing. Task-run UUIDs still correlate graphs,
checkpoints, manifests, and model calls.

Narration never gates the next phase: a narration failure is recorded
in the report while the phase completes. S1 worlds are S1-driven; do
not mix Stage 0 advancement on the same world (both share the run
space and the clock).
"""

from __future__ import annotations

import asyncio
import contextlib
import difflib
import hashlib
import json
import logging
import random
import time
import weakref
from collections import Counter
from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import UUID, uuid4, uuid5

from sqlalchemy.exc import IntegrityError

from worldsim.application.commands.director import accept_decision, open_place
from worldsim.application.commands.inventory import move_item
from worldsim.application.commands.knowledge import fold_claim
from worldsim.application.commands.party import recruit_companion
from worldsim.application.conditions import tick_conditions
from worldsim.application.context.assembler import assemble, to_manifest_dict
from worldsim.application.geography import PLACE_MAPS, StorySpot, story_spots
from worldsim.application.graphs.character import (
    CHARACTER_PROMPT_VERSION,
    CharacterGraphDeps,
    build_character_graph,
    load_character_prompt,
    precheck_action,
)
from worldsim.application.graphs.director import (
    DIRECTOR_PROMPT_VERSION,
    DirectorGraphDeps,
    build_director_graph,
    load_director_prompt,
)
from worldsim.application.graphs.narrate import (
    NARRATOR_PROMPT_VERSION,
    RECAP_FACT_KEY,
    SETTING_FACT_KEYS,
    SPOTS_FACT_KEY,
    NarratorGraphDeps,
    attempt_speech_facts,
    build_narration_graph,
    communication_facts,
    dedupe_narration_facts,
    fallback_beats,
    load_narrator_prompt,
    move_note_facts,
)
from worldsim.application.graphs.reaction import (
    REACTION_PROMPT_VERSION,
    ReactionGraphDeps,
    build_reaction_graph,
    load_reaction_prompt,
)
from worldsim.application.graphs.resolve import (
    RESOLVER_PROMPT_VERSION,
    ResolverGraphDeps,
    build_resolve_graph,
    load_resolver_prompt,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.graphs.summary import (
    DIGEST_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
    SummaryGraphDeps,
    accepted_ids,
    build_summary_graph,
    load_digest_prompt,
    load_summary_prompt,
    tag_sources,
    untag,
)
from worldsim.application.images import world_style_pack
from worldsim.application.interventions import (
    apply_batch,
    claim_for_boundary,
    plan_attempts,
    record_attempts,
)
from worldsim.application.orchestration import phase_reads
from worldsim.application.orchestration.background import BackgroundNarration
from worldsim.application.orchestration.framing import frame_gateways
from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id
from worldsim.application.orchestration.settle_xp import award_settled_hooks
from worldsim.application.pictures import MomentWords, judge_moment, plan_moments, queue_moment
from worldsim.application.ports.local_models import LocalModels, LocalModelsUnavailable
from worldsim.application.ports.model_gateway import ModelGateway, ModelProfile
from worldsim.application.ports.writer import Writer
from worldsim.application.settings.resolution import (
    PinnedRuntime,
    SamplingParams,
    resolve_controlled_character,
    resolve_pin,
    sampling_from_pin,
)
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.gateway import TracedGateway
from worldsim.application.tracing.service import ManifestSpec, TraceService
from worldsim.application.transactions.canonical import (
    CanonicalTransaction,
    CommitRequest,
    MemorySpec,
    ObservationSpec,
    canonical_input_hash,
)
from worldsim.application.transactions.scenes import build_scene_commit, observation_spec
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.activities import Activity, effective_progress
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.commands import (
    ActionIntent,
    AppealAction,
    CommunicateAction,
    InteractAction,
    MoveAction,
    SparAction,
    TakeAction,
    TransferAction,
)
from worldsim.domain.context import ContextEnvelope, ContextRequest, SourceCandidate
from worldsim.domain.director import (
    ADDED_PLACES_CONFIG_KEY,
    DIRECTOR_COOLDOWN_PHASES,
    MAX_ADDED_PLACES,
    MAX_SPAWNED_NPCS,
    SPAWNED_CONFIG_KEY,
    AddedPlace,
    DirectorDecision,
    should_trigger,
)
from worldsim.domain.effects import (
    AdvanceClockEffect,
    DomainEffect,
    HookSettledEffect,
    MoveEntityEffect,
    ResourceAdjustedEffect,
    SkillProgressEffect,
)
from worldsim.domain.enums import (
    ActionFamily,
    ActivityKind,
    ActivityStatus,
    EventType,
    LifeStatus,
    NarrativeStatus,
    PhaseRunState,
    ResolutionOutcome,
    ResourceKind,
    ScheduleStatus,
    UserRole,
    Visibility,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.geography import spot_named
from worldsim.domain.ids import (
    derive_attempt_id,
    derive_combat_event_id,
    derive_intent_id,
    derive_task_id,
    new_activity_id,
    new_arc_id,
    new_digest_id,
    new_hook_id,
    new_monster_id,
    new_narration_id,
    new_summary_id,
)
from worldsim.domain.intentions import (
    STREAK_TURNS,
    CharacterIntention,
    card_drives,
    extract_intention,
    streak_note,
)
from worldsim.domain.items import ItemDefinition, load_item_definitions
from worldsim.domain.knowledge import normalize
from worldsim.domain.memory import (
    CITE_BUMP_KEY,
    DEFAULT_CITE_BUMP,
    DEFAULT_HALF_LIFE_PHASES,
    DEFAULT_PROMOTION_MAX_PER_DAY,
    DEFAULT_PROMOTION_MAX_TOTAL,
    DEFAULT_PROMOTION_MIN_AGE,
    DEFAULT_PROMOTION_THRESHOLD,
    DEFAULT_RECENT_PHASES,
    DEFAULT_RELEVANCE_WEIGHT,
    DEFAULT_SALIENCE_FLOOR,
    DIGEST_SCORE,
    HALF_LIFE_PHASES_KEY,
    MAX_SALIENCE,
    PROMOTION_ENABLED_KEY,
    PROMOTION_MAX_PER_DAY_KEY,
    PROMOTION_MAX_TOTAL_KEY,
    PROMOTION_MIN_AGE_KEY,
    PROMOTION_THRESHOLD_KEY,
    RECALL_OLD_LIMIT,
    RECALL_OLD_MIN_SIMILARITY,
    RECENT_PHASES_KEY,
    RELEVANCE_WEIGHT_KEY,
    SALIENCE_FLOOR_KEY,
    MemoryDigest,
    relevance,
    score_salience,
)
from worldsim.domain.narration import NarrationBeat
from worldsim.domain.narrative import NarrativeHook
from worldsim.domain.party import (
    Monster,
    chooser_keys,
    down_line,
    fight_keys,
    fight_over_line,
    foes_line,
    foes_on,
    party_in_scene,
    party_name_key,
    present_keys,
    slots_line,
)
from worldsim.domain.perception import (
    Disclosure,
    FactChannel,
    FactVisibility,
    ObservableEvent,
    Observation,
    ObservationFact,
    PerceivedFact,
    RecentMemory,
)
from worldsim.domain.phases import PhaseRun, PhaseSnapshot, SnapshotCharacter
from worldsim.domain.progress import TRAINING_STAMINA_COST, ItemInstance
from worldsim.domain.relationships import Relationship, describe
from worldsim.domain.rules.dnd import (
    DataTables,
    MonsterState,
    TagOutcome,
    armor_ac,
    build_sheet_summary,
    combat_rolls_json,
    dnd_party_prompt,
    dnd_story_rules_text,
    load_data,
    parse_recruit_tags,
    resolve_narration_tags,
    roll_attack,
    roll_damage,
    weapon_attack_bonus,
)
from worldsim.domain.rules.dnd.data import dict_field, entry, str_field, table
from worldsim.domain.rules.dnd.deeds import Deed, looks_like_deed
from worldsim.domain.rules.dnd.invites import (
    accepts,
    companion_description,
    invitation_note,
    is_invitation,
)
from worldsim.domain.rules.dnd.party import MAX_PARTY_SIZE
from worldsim.domain.rules.dnd.progress import long_rest
from worldsim.domain.rules.dnd.sheets import weapon_damage
from worldsim.domain.rules.grounding import grounded_move
from worldsim.domain.rules.meetups import resolve_meetups
from worldsim.domain.rules.mentions import MENTION_MODEL, unmapped_places
from worldsim.domain.rules.perception import permitted_facts
from worldsim.domain.rules.phases import is_quiet_phase
from worldsim.domain.rules.repeats import (
    Exchange,
    answered_exchanges,
    repeated,
    retry_note,
    settled_note,
)
from worldsim.domain.rules.resources import rest_recovery, restore, spend
from worldsim.domain.rules.routes import with_route
from worldsim.domain.rules.scenes import assemble_scenes
from worldsim.domain.rules.views import WorldView
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene
from worldsim.domain.settings import LOCAL_OPERATOR
from worldsim.domain.summaries import DailySummary, day_range, fallback_text
from worldsim.domain.tasks import Lease
from worldsim.domain.time import (
    PHASES_PER_DAY,
    absolute_index,
    phase_label,
    split_absolute,
    utcnow,
)
from worldsim.domain.tracing import ManifestSource
from worldsim.domain.world import Location, Route

#: Resolved from this file like the prompt paths (and like
#: interfaces/http/state.py), so loading works from any working directory.
DND_DATA_DIR = Path(__file__).resolve().parents[5] / "content" / "dnd"


#: Run states that refuse advancement (same bucket as Stage 0).
_BLOCKED_RUN_STATES = frozenset({"paused", "terminal_failed", "cancelled"})

#: World-config key opting a world into structured narration: committed
#: facts are voiced through deterministic fallback beats with no narrator
#: model call. Absent or any other value keeps model narration.
NARRATION_MODE_KEY = "narration.mode"

#: Config value selecting structured narration (see NARRATION_MODE_KEY).
NARRATION_MODE_STRUCTURED = "structured"


class GatewayFactory(Protocol):
    """Role (character/reaction/resolver/narrator) to gateway."""

    def __call__(self, role: str) -> ModelGateway: ...


class PinGatewayFactory(Protocol):
    """Pinned story runtime (revision plus connection) to gateway."""

    def __call__(self, role: str, pin: PinnedRuntime) -> ModelGateway: ...


@dataclass(frozen=True)
class PhaseRuntime:
    """Everything one phase run executes with, captured once at admission.

    Pinned stories run their revision model through a gateway built
    from the pinned connection; unpinned stories keep the environment
    gateways. Each run builds its own instances, so no story can leak
    its selection into another through shared gateway state.
    """

    sampling: SamplingParams
    gateways: dict[str, ModelGateway]
    profiles: dict[str, ModelProfile]
    pin: PinnedRuntime | None
    controlled_character_id: UUID | None = None

    @property
    def pin_id(self) -> str | None:
        """Requested pin identity for the audit chain, if any."""
        return str(self.pin.profile.id) if self.pin is not None else None

    @property
    def pin_revision(self) -> int | None:
        """Requested pin revision for the audit chain, if any."""
        return self.pin.profile.revision if self.pin is not None else None


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


@dataclass(frozen=True)
class SceneOutcome:
    scene_id: UUID
    event_id: UUID
    resolution_outcome: str
    narration: str


@dataclass(frozen=True)
class PreparedScene:
    """A scene's model work, ready to commit."""

    members: list[Intent]
    attempts: list[Attempt]
    reactions: list[Reaction]
    resolution: Resolution
    live_versions: dict[str, int]
    observations: list[ObservationSpec]
    memories: list[MemorySpec]


_phase_log = logging.getLogger("worldsim.phase")

#: Completion-cap floors for roles whose output grows with the world:
#: summaries and digests cite many observation ids, the resolver lists
#: effects for every intent, the director emits hook plus arc objects.
#: The shared sampling cap (default 512) truncates these mid-JSON. The
#: narrator sizes its own cap from the beat budget (narrator_max_tokens).
#: Summaries got 1536 after 9 of 71 traced summaries stopped at 1024 mid-JSON
#: (8 of 12 on Venice, whose summaries run ~935 tokens), each followed by a
#: repair that truncated again (docs/evidence/perf-llm-001).
ROLE_MAX_TOKEN_FLOORS: dict[str, int] = {"summary": 1536, "resolver": 1024, "director": 768}


def role_max_tokens(configured: int, role: str) -> int:
    """Configured cap raised to the role's floor, never above 4096."""
    return min(max(configured, ROLE_MAX_TOKEN_FLOORS.get(role, 0)), 4096)


ITEM_CATALOG_PATH = Path(__file__).resolve().parents[5] / "content" / "definitions" / "items.json"
_item_catalog_cache: dict[str, ItemDefinition] | None = None


def _item_catalog() -> dict[str, ItemDefinition]:
    global _item_catalog_cache
    if _item_catalog_cache is None:
        try:
            _item_catalog_cache = load_item_definitions(ITEM_CATALOG_PATH)
        except (OSError, ValueError):
            _item_catalog_cache = {}
    return _item_catalog_cache


def item_label(item: ItemInstance) -> str:
    """Display name: the item's own, else the catalog's, else its key."""
    if item.name:
        return item.name
    known = _item_catalog().get(item.item_key)
    return known.name if known is not None else item.item_key.replace("_", " ")


def item_description(item: ItemInstance) -> str:
    """The item's own description, else the catalog's, else nothing."""
    known = _item_catalog().get(item.item_key)
    return item.description or (known.description if known is not None else "")


def item_line(item: ItemInstance) -> str:
    """Name, short description and id, as listed to a character."""
    about = item_description(item)
    count = f" x{item.quantity}" if item.quantity > 1 else ""
    detail = f" — {about}" if about else ""
    return f"{item_label(item)}{count}{detail} (item_id {item.id})"


def scene_surroundings(
    members: Sequence[Intent],
    characters: Sequence[Character],
    locations: Sequence[Location],
    items: Sequence[ItemInstance],
    hooks: Sequence[Any],
) -> list[str]:
    """What the resolver should know is at hand where each actor stands.

    Without it every attempt was judged against an imagined place: a play
    session "found" the peddler's crate at the Hearth while everyone said
    it was at the Market.
    """
    names = {loc.id: loc.name for loc in locations}
    where = {c.id: c.location_id for c in characters}
    notes: list[str] = []
    for place_id in dict.fromkeys(where.get(m.author_character_id) for m in members):
        if place_id is None:
            continue
        people = [
            c.name
            for c in characters
            if c.location_id == place_id and c.life_status == LifeStatus.ALIVE
        ]
        lying = [item_label(i) for i in items if i.owner_id is None and i.location_id == place_id]
        held = [
            f"{item_label(i)} (held by {next(c.name for c in characters if c.id == i.owner_id)})"
            for i in items
            if i.owner_id is not None and where.get(i.owner_id) == place_id
        ]
        notes.append(
            f"At {names.get(place_id, 'this place')}: {', '.join(people) or 'nobody else'}"
            f"; lying here: {', '.join(lying) or 'nothing'}"
            f"; carried here: {', '.join(held) or 'nothing'}."
        )
    for hook in hooks:
        if hook.status != NarrativeStatus.CLOSED:
            notes.append(f"Open rumour (hook_id {hook.id}): {hook.title}. {hook.purpose}".strip())
    return notes


#: Character budgets per context section for decisions. The 2,000-char
#: default dropped 15-24 observations per call by beat 12 of a play
#: session (manifests), losing what was said a few beats earlier;
#: continuity sections get room, the rest keep the default.
#: Scenes of one turn the moment writer reads in a watched story.
WATCHED_SCENES_JUDGED = 3

#: Salient observations and memories from before the recent window that a
#: context still considers, newest first. Each row costs ~0.02 ms to rank
#: on every call, and the salient set has no time limit; at the live
#: salience rate (~7%) this binds only after ~2,800 turns (perf-reads-001).
OLDER_SALIENT_KEPT = 200

DECISION_SECTION_BUDGETS = {"observations": 6000, "memories": 3000, "lore": 3000, "goals": 2500}


#: How long (in phases, ten a day) characters still talk of a settled rumour.
SETTLED_MEMORY_PHASES = 20


def _with_pronouns(character_id: UUID, pronouns: Mapping[UUID, str] | None) -> str:
    stated = (pronouns or {}).get(character_id)
    return f"{stated}, " if stated else ""


def whereabouts(
    characters: Sequence[Character], participants: Sequence[str], places: Mapping[UUID, str]
) -> dict[str, str]:
    """Name -> place for each scene participant, as the world stands now."""
    wanted = set(participants)
    return {
        c.name: places.get(c.location_id, "the road") for c in characters if str(c.id) in wanted
    }


def scene_location(
    scene: Scene, starts: Mapping[UUID, UUID], effects: Sequence[DomainEffect]
) -> UUID | None:
    """Where a scene happened: where everyone ends up when that is one place.

    It was the first participant's starting place, so a traveller (sorted
    first) who walked to a friend recorded the scene, and its painting, at
    the place they left (the narrator already set it where they met).
    """
    ends = dict(starts)
    for effect in effects:
        if isinstance(effect, MoveEntityEffect):
            for moved in effect.affected_ids:
                ends[moved] = effect.to_location_id
    places = {ends.get(p.character_id) for p in scene.participants}
    if len(places) == 1 and None not in places:
        return places.pop()
    return starts.get(scene.participants[0].character_id) if scene.participants else None


def scene_place_facts(start: str | None, ends: Mapping[str, str]) -> list[tuple[str, str]]:
    """The scene's setting for the narrator: one place, or where it ends up.

    Scorecard-era bug: a traveller and the friend waiting for them shared
    a scene "at" the traveller's starting place, and the narrator had the
    friend "stay behind" somewhere they never were.
    """
    facts: list[tuple[str, str]] = []
    finals = set(ends.values())
    if len(finals) == 1 and start and next(iter(finals)) != start:
        end = next(iter(finals))
        facts.append(("place", f"The scene takes place at {end}."))
    elif start:
        facts.append(("place", f"The scene takes place at {start}."))
    # Only when people end up apart is it worth saying where each one is;
    # otherwise the narrator just repeats "both remain at the Market".
    if len(finals) > 1:
        listed = "; ".join(f"{name} at {place}" for name, place in sorted(ends.items()))
        facts.append(("whereabouts", f"By the end of the scene: {listed}."))
    return facts


def identity_text(card: CharacterCard) -> str:
    """A character's card as their own identity line, pronouns after the name."""
    named = f"{card.name} ({card.pronouns})" if card.pronouns else card.name
    return f"{named}. {card.appearance} {card.personality} {card.background}".strip()


def pronoun_line(characters: Sequence[Character], pronouns: Mapping[UUID, str]) -> str:
    """How to refer to each person in a scene; unstated means name or they/them."""
    parts = [
        f"{c.name}: {pronouns[c.id]}"
        if c.id in pronouns
        else f"{c.name}: not stated (use the name or they/them)"
        for c in sorted(characters, key=lambda c: c.name)
    ]
    return "Pronouns — " + "; ".join(parts) + "."


#: Card versions never change once written, so a beat reads each one once.
CardCache = dict[tuple[UUID, int], CharacterCard]


@dataclass(frozen=True)
class _WorldView:
    """What every context builder of a phase reads alike (phase_reads)."""

    config: dict[str, object]
    now_index: int
    hooks: list[NarrativeHook]
    everyone: list[Character]
    away: set[UUID]
    locations: list[Location]

    def place(self, location_id: UUID | None) -> Location | None:
        return next((loc for loc in self.locations if loc.id == location_id), None)

    def person(self, character_id: UUID) -> Character | None:
        return next((c for c in self.everyone if c.id == character_id), None)


@dataclass(frozen=True)
class _Mind:
    """A character's own remembered material, shared within a phase (phase_reads)."""

    observations: list[Observation]
    memories: list[RecentMemory]
    relationships: list[Relationship]
    digests: list[MemoryDigest]
    families: list[str]


async def _card_of(uow: Any, character: Character, cards: CardCache | None) -> CharacterCard:
    """The character's current card, read once per beat when given a cache."""
    key = (character.id, character.card_version)
    if cards is not None and key in cards:
        return cards[key]
    card = await uow.characters.get_card(character.id, character.card_version)
    if cards is not None:
        cards[key] = card
    return card


async def _pronouns_of(
    uow: Any, characters: Sequence[Character], cards: CardCache | None = None
) -> dict[UUID, str]:
    """Stated pronouns of these characters (unstated ones are left out)."""
    found: dict[UUID, str] = {}
    for character in characters:
        card = await _card_of(uow, character, cards)
        if card.pronouns:
            found[character.id] = card.pronouns
    return found


def surroundings_text(
    place: Location,
    place_names: Mapping[UUID, str],
    characters: Sequence[Character],
    viewer_id: UUID,
    items_here: Sequence[ItemInstance] = (),
    pronouns: Mapping[UUID, str] | None = None,
) -> str:
    """What a character perceives where they stand: the place, its routes
    by name and id, and who else is visibly present (living, same place).

    Ids are listed because move, communicate, spar and transfer must name
    them; without them the only actions a model can form are wait and
    observe.
    """
    routes = ", ".join(
        f"{place_names.get(r.destination_location_id, 'unknown place')} "
        f"(location_id {r.destination_location_id}{road_note(r)})"
        for r in place.routes
    )
    present = ", ".join(
        f"{c.name} ({_with_pronouns(c.id, pronouns)}character_id {c.id})"
        for c in sorted(characters, key=lambda c: c.id.hex)
        if c.id != viewer_id and c.location_id == place.id and c.life_status == LifeStatus.ALIVE
    )
    where = f"{place.name}, {place.region}" if place.region else place.name
    things = "; ".join(item_line(i) for i in items_here)
    return (
        f"You are at {where}. From here you can travel to: {routes or 'nowhere'}. "
        f"Present here: {present or 'no one else'}."
        + (f" Things lying here: {things}." if things else "")
    )


@contextmanager
def _timed(timings: dict[str, int], stage: str) -> Generator[None]:
    """Accumulate wall-clock milliseconds for one phase stage."""
    started = time.monotonic()
    try:
        yield
    finally:
        elapsed = int((time.monotonic() - started) * 1000)
        timings[stage] = timings.get(stage, 0) + elapsed


@dataclass(frozen=True)
class Stage1PhaseReport:
    run_id: UUID
    world_id: UUID
    absolute_index: int
    snapshot_id: UUID
    scenes: list[SceneOutcome] = field(default_factory=list)
    duplicate: bool = False
    quiet: bool = False
    #: Wall-clock ms per stage (probe, director, decide, react, resolve,
    #: narrate, scenes, day_end, total); empty on duplicate replays.
    timings_ms: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SealedPhase:
    """Shared snapshot plus the sealed versions and places decisions use."""

    snapshot_id: UUID
    versions: dict[str, int]
    locations: dict[UUID, UUID]


def _snapshot_hash(
    world_id: UUID, run_id: UUID, absolute: int, world_version: int, members: list[tuple[str, int]]
) -> str:
    canonical = json.dumps(
        {
            "world_id": world_id.hex,
            "run_id": run_id.hex,
            "absolute_index": absolute,
            "world_version": world_version,
            "characters": sorted(members),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _config_float(config: dict[str, object], key: str, default: float) -> float:
    """World-config float with a recorded default; wrong types fall back."""
    raw = config.get(key)
    return float(raw) if isinstance(raw, (int, float)) else default


def _config_int(config: dict[str, object], key: str, default: int) -> int:
    """World-config int with a recorded default; wrong types fall back."""
    raw = config.get(key)
    return int(raw) if isinstance(raw, int) else default


#: Recent scene events the director reads, and beats counted for a stall.
DIRECTOR_RECENT_EVENTS = 8
#: Families that leave the world as it was.
_IDLE_FAMILIES = frozenset({ActionFamily.WAIT, ActionFamily.OBSERVE, ActionFamily.REST})


async def _recent_happenings(
    uow: Any, world_id: UUID, *, with_lines: bool = True
) -> tuple[list[str], int, int, list[str]]:
    """Latest scene narrations (oldest first) and two stall signals.

    Idle streak: recent beats where every attempt was a wait, observe or
    rest. Talk streak: recent beats where nothing but conversation (and
    idling) happened — no move, take, handover, spar or appeal — which is
    how a loop of re-asked questions looks from outside.

    Reads the last 60 events' scenes and intents in a handful of batched
    queries (it ran 3 queries per event plus one per intent, ~600 a beat,
    docs/evidence/perf-beat-001). ``with_lines=False`` skips the narration
    lines for callers that only want what was said.
    """
    high = await uow.events.max_sequence(world_id)
    events = await uow.events.list_range(world_id, max(0, high - 60), 60)
    scenes = [e for e in events if e.event_type == EventType.ACTION_RESOLVED]
    lines: list[str] = []
    if with_lines:
        told = scenes[-DIRECTOR_RECENT_EVENTS:]
        beats_by_event = await uow.scenes.narrations_for_events([e.id for e in told])
        for event in told:
            beats = beats_by_event.get(event.id, [])
            if beats:
                text = " ".join(b.text for b in beats)
                lines.append(f"{phase_label(event.absolute_index)}: {text[:240]}")
    run_scenes = [e for e in scenes if e.phase_run_id is not None]
    by_event: dict[UUID, list[Scene]] = {}
    for scene in await uow.scenes.scenes_for_events([e.id for e in run_scenes]):
        if scene.event_id is not None:
            by_event.setdefault(scene.event_id, []).append(scene)
    intents = await uow.scenes.get_intents(
        [i for told in by_event.values() for scene in told for i in scene.intent_ids]
    )
    idle_by_index: dict[int, bool] = {}
    talk_by_index: dict[int, bool] = {}
    said: list[str] = []  # speech and attempts, for places mentioned but not mapped
    for event in run_scenes:
        idle = idle_by_index.get(event.absolute_index, True)
        talk = talk_by_index.get(event.absolute_index, True)
        for scene in by_event.get(event.id, []):
            for intent_id in scene.intent_ids:
                intent = intents.get(intent_id)
                if intent is None:
                    intent = await uow.scenes.get_intent(intent_id)  # raises as before
                family = intent.action.family
                if isinstance(intent.action, CommunicateAction):
                    said.append(intent.action.topic)
                elif isinstance(intent.action, InteractAction):
                    said.append(intent.action.attempt)
                if family not in _IDLE_FAMILIES:
                    idle = False
                if family not in _IDLE_FAMILIES and family != ActionFamily.COMMUNICATE:
                    talk = False
        idle_by_index[event.absolute_index] = idle
        talk_by_index[event.absolute_index] = talk
    return lines, _streak(idle_by_index), _streak(talk_by_index), said


#: What the director reads when nothing is open (a long session sat 23 beats without a lead).
NO_OPEN_HOOKS = "none (nobody has a lead to follow: propose one)"

#: Lines of story-so-far the director gets from before its recent window.
STORY_SO_FAR_LINES = 6
#: How far back (in events) the story-so-far looks.
STORY_SO_FAR_EVENTS = 240


def spread[T](items: Sequence[T], count: int) -> list[T]:
    """Up to ``count`` items evenly across the sequence, first and last kept."""
    if len(items) <= count:
        return list(items)
    if count <= 1:
        return [items[-1]] if count == 1 else []
    step = (len(items) - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]


#: Attempts that are not news for a story-so-far.
_IDLE_ATTEMPTS = ("attempt:wait", "attempt:observe", "attempt:rest")


async def _story_so_far(uow: Any, world_id: UUID) -> list[str]:
    """What happened before the director's recent window, spread through time.

    One line per scene where someone did something, made of its attempts
    ("Ash says to Old Marg: one more heave; Old Marg tries to free the
    wheel: it half works"). Narration openings were mostly scenery, and
    older events carry no idle flag, so attempts decide. The recent
    window already shows the latest scenes in full, so they are left out.
    """
    high = await uow.events.max_sequence(world_id)
    events: list[WorldEvent] = await uow.events.list_range(
        world_id, max(0, high - STORY_SO_FAR_EVENTS), STORY_SO_FAR_EVENTS
    )
    scenes = [e for e in events if e.event_type == EventType.ACTION_RESOLVED]
    told: list[tuple[int, str]] = []
    worth = [e for e in scenes[:-DIRECTOR_RECENT_EVENTS] if e.summary.get("idle") != "1"]
    # One query for the whole window (it was one per event, up to 240).
    seen_by_event = await uow.perception.observations_for_events([e.id for e in worth])
    for event in worth:
        seen: list[str] = []
        for obs in seen_by_event.get(event.id, []):
            for fact in obs.facts:
                if (
                    fact.key.startswith("attempt:")
                    and not fact.key.startswith(_IDLE_ATTEMPTS)
                    and fact.value not in seen
                ):
                    seen.append(fact.value)
        if seen:
            told.append((event.absolute_index, _clip("; ".join(seen), 200)))
    return [f"{phase_label(index)}: {line}" for index, line in spread(told, STORY_SO_FAR_LINES)]


def _streak(flags: Mapping[int, bool]) -> int:
    """How many of the most recent beats in a row have the flag set."""
    count = 0
    for index in sorted(flags, reverse=True):
        if not flags[index]:
            break
        count += 1
    return count


def director_summary(
    index: int,
    characters: Sequence[Character],
    locations: Sequence[Location],
    hooks: Sequence[Any],
    arcs: Sequence[Any],
    recent: Sequence[str],
    quiet_streak: int,
    intentions: Mapping[UUID, str] | None = None,
    *,
    talk_streak: int = 0,
    earlier: Sequence[str] = (),
    journeys: Mapping[UUID, UUID] | None = None,
) -> str:
    """What the director sees: who is where (with ids), threads, the story so far."""
    place = {loc.id: loc.name for loc in locations}
    plans = intentions or {}
    roads = journeys or {}

    def where(c: Character) -> str:
        if c.id in roads:
            return f"on the road to {place.get(roads[c.id], 'somewhere')}"
        return f"at {place.get(c.location_id, 'somewhere')}"

    cast = "; ".join(
        f"{c.name} (id {c.id}, {where(c)}"
        + (f", intends: {plans[c.id]}" if c.id in plans else "")
        + ")"
        for c in characters
        if c.life_status == LifeStatus.ALIVE
    )
    places = ", ".join(f"{loc.name} (id {loc.id})" for loc in locations)
    open_hooks = "; ".join(
        f"{h.title} (hook_id {h.id}): {h.purpose}".strip(": ")
        for h in hooks
        if h.status != NarrativeStatus.CLOSED
    )
    open_arcs = "; ".join(a.title for a in arcs if a.status != NarrativeStatus.CLOSED)
    # Settled matters stay in view so they are not proposed all over again.
    settled = [
        f"- {h.title}: {h.ending}".strip()
        for h in hooks
        if h.status == NarrativeStatus.CLOSED and getattr(h, "ending", None)
    ][-STORY_SO_FAR_LINES:]
    lines = [
        f"Phase {index} ({phase_label(index)}).",
        f"Characters: {cast or 'none'}.",
        f"Places: {places or 'none'}.",
        f"Open hooks: {open_hooks or NO_OPEN_HOOKS}.",
        f"Open arcs: {open_arcs or 'none'}.",
        *(["Settled so far:", *settled] if settled else []),
        *(
            ["Story so far, before the recent happenings:", *[f"- {e}" for e in earlier]]
            if earlier
            else []
        ),
        "Recent happenings, oldest first:",
        *([f"- {line}" for line in recent] or ["- nothing yet"]),
        f"Idle beats in a row: {quiet_streak} (every character only waited, watched or rested).",
        f"Talk-only beats in a row: {talk_streak} (conversation, but nobody moved, took, "
        "gave or did anything else).",
    ]
    return "\n".join(lines)


def _suggested_place(
    unmapped: Sequence[tuple[str, int]],
    characters: Sequence[Character],
    locations: Sequence[Location],
    places_left: int,
) -> tuple[str, Location] | None:
    """The most-mentioned unmapped place, named, and the place it joins.

    It connects from where most living characters stand.
    """
    if not unmapped or places_left <= 0 or not locations:
        return None
    name = " ".join(w if w.endswith("'s") else w.capitalize() for w in unmapped[0][0].split())
    crowd = Counter(c.location_id for c in characters if c.life_status == LifeStatus.ALIVE)
    by_id = {loc.id: loc for loc in locations}
    origin = next((by_id[p] for p, _n in crowd.most_common() if p in by_id), locations[0])
    return name, origin


def _place_suggestion(
    unmapped: Sequence[tuple[str, int]],
    characters: Sequence[Character],
    locations: Sequence[Location],
    places_left: int,
) -> str:
    """A ready-to-use new_location for the most-mentioned unmapped place.

    Playtest scorecards showed the director acknowledging such a place
    ("The Mill Door Stands Open") yet spawning a character instead of
    adding it; spelling out the fields makes adding it the easy path.
    """
    suggested = _suggested_place(unmapped, characters, locations, places_left)
    if suggested is None:
        return ""
    name, origin = suggested
    return (
        f'\nSuggested: add "{name}" — for example "place": {{"name": "{name}", '
        f'"connect_to": "{origin.id}"}} (reached from {origin.name}).'
    )


#: Mentions after which a place someone sets out for opens (see _open_wanted_place).
OPEN_PLACE_MENTIONS = 3

#: How far back (phases) answered exchanges count, and how many are shown.
ANSWERED_WINDOW_PHASES = 10
ANSWERED_SHOWN = 3

#: A recap older than this many phases is no longer "just now".
PREVIOUSLY_MAX_AGE = 3
#: How much of the earlier narration the recap carries.
PREVIOUSLY_CHARS = 320
#: Fallback narration with nothing in it; not worth recalling.
_NOTHING_OF_NOTE = "Nothing of note occurs."


async def _previously(uow: Any, world_id: UUID, event_id: UUID) -> str | None:
    """The last narrated scene that shared someone with this one, if recent.

    Gives the narrator continuity: without it every beat re-introduces
    the room ("The quiet of Hearth settles around you") as if new.
    """
    event = await uow.events.get_event(event_id)
    people = set(event.participant_ids)
    if not people:
        return None
    high = await uow.events.max_sequence(world_id)
    window = await uow.events.list_range(world_id, max(0, high - 40), 40)
    for prior in reversed(window):
        if prior.event_type != EventType.ACTION_RESOLVED or prior.id == event_id:
            continue
        if prior.absolute_index >= event.absolute_index:
            continue  # this beat's other scenes happen alongside, not before
        if event.absolute_index - prior.absolute_index > PREVIOUSLY_MAX_AGE:
            return None
        if not people & set(prior.participant_ids):
            continue
        beats = await uow.scenes.narrations_for_event(prior.id)
        text = " ".join(b.text for b in beats if b.text != _NOTHING_OF_NOTE).strip()
        if text:
            return f"{phase_label(prior.absolute_index)}: {_clip(text, PREVIOUSLY_CHARS)}"
    return None


async def _last_spot(
    uow: Any, world_id: UUID, event_id: UUID, location_id: UUID, spots: Sequence[StorySpot]
) -> StorySpot | None:
    """The spot these people's latest scenes here were set at: the newest
    earlier scene shared with them that named one, while they stayed in
    this place."""
    event = await uow.events.get_event(event_id)
    people = set(event.participant_ids)
    if not people or not spots:
        return None
    high = await uow.events.max_sequence(world_id)
    window = await uow.events.list_range(world_id, max(0, high - 40), 40)
    for prior in reversed(window):
        if prior.event_type != EventType.ACTION_RESOLVED or prior.id == event_id:
            continue
        if prior.absolute_index >= event.absolute_index or not people & set(prior.participant_ids):
            continue
        if prior.summary.get("location_id") != str(location_id):
            return None  # they came from elsewhere
        beats = await uow.scenes.narrations_for_event(prior.id)
        key = spot_named(" ".join(b.text for b in beats), [(s.key, s.name) for s in spots])
        if key is not None:
            return next((s for s in spots if s.key == key), None)
        # A scene that named no spot leaves them where they were.
    return None


def journey_span(phases: int) -> str:
    """'3 phases', 'about 1 day', 'about 2 days and 4 phases' (ten phases a day)."""
    days, rest = divmod(phases, 10)
    if days == 0:
        return f"{phases} phase{'s' if phases > 1 else ''}"
    return f"about {days} day{'s' if days > 1 else ''}" + (f" and {rest} phases" if rest else "")


def road_note(route: Route) -> str:
    """How long and how tiring a road is, for whoever might take it."""
    if route.duration_phases <= 1 and route.stamina_cost == 0:
        return ""
    cost = f", costs {route.stamina_cost} stamina" if route.stamina_cost else ""
    return f"; a journey of {journey_span(route.duration_phases)}{cost}"


def journey_fact(name: str, destination: str, phases: int) -> str:
    """What the narrator is told of a traveller who has only set off."""
    span = journey_span(phases)
    return (
        f"{name} sets off on the road to {destination}, a journey of {span}: "
        f"{name} leaves this place now and has not arrived."
    )


def split_journeys(
    effects: list[DomainEffect], roads: Mapping[UUID, Route]
) -> tuple[list[DomainEffect], list[tuple[MoveEntityEffect, Route]]]:
    """Moves along roads longer than one phase become journeys, not effects.

    Their stamina effect stays: the traveller pays it on setting off.
    """
    kept: list[DomainEffect] = []
    journeys: list[tuple[MoveEntityEffect, Route]] = []
    for effect in effects:
        route = (
            roads.get(effect.route_id)
            if isinstance(effect, MoveEntityEffect) and effect.route_id
            else None
        )
        if isinstance(effect, MoveEntityEffect) and route is not None and route.duration_phases > 1:
            journeys.append((effect, route))
        else:
            kept.append(effect)
    return kept, journeys


async def on_the_road(uow: Any, world_id: UUID) -> set[UUID]:
    """Characters on an active journey: at no place until they arrive."""
    return {
        a.character_id
        for a in await uow.activities.list_active_for_world(world_id)
        if a.kind == ActivityKind.TRAVEL
    }


async def _event_place(uow: Any, event_id: UUID) -> Location | None:
    """The place a scene event recorded (None for older events)."""
    event = await uow.events.get_event(event_id)
    raw = event.summary.get("location_id")
    if not raw:
        return None
    try:
        return cast("Location", await uow.locations.get(UUID(raw)))
    except (DomainError, ValueError):
        return None


def spots_fact(spots: Sequence[StorySpot], last: StorySpot | None = None) -> str | None:
    """The spots inside the scene's place, for the narrator to set it at one;
    where these people last were, so a scene does not hop without cause."""
    if not spots:
        return None
    listed = "; ".join(f"{s.name} ({s.kind})" if s.kind else s.name for s in spots)
    stay = (
        f" They were last at {last.name}: keep the scene there unless what happens moves them."
        if last is not None
        else ""
    )
    return (
        f"Spots in this place: {listed}. Set the scene at the one spot that fits "
        f"what happens, and name it in the first beat as written here.{stay}"
    )


def _recall_focus(
    character: Character,
    place: str,
    present: list[str],
    intention: str | None,
    carried: list[str],
    latest: list[str],
) -> str:
    """What is going on for one character now, as a recall query."""
    parts = [f"{character.name} is at {place}."]
    if present:
        parts.append(f"With {', '.join(present)}.")
    if intention:
        parts.append(f"Means to: {intention}")
    if carried:
        parts.append(f"Carrying {', '.join(carried)}.")
    parts.extend(latest)
    return " ".join(parts)[:2000]


def _observation_line(index: int, key: str, value: str) -> str:
    """Time-labelled observation; attempt and reply lines are already prose."""
    if key.startswith(("attempt:", "reply:")):
        return f"{phase_label(index)}: {value}"
    return f"{phase_label(index)}: {key}: {value}"


#: Observation facts hold at most 512 characters.
_FACT_CHARS = 512


def _clip(text: str, limit: int = _FACT_CHARS) -> str:
    """Fit a perceived line into an observation fact, marking any cut."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


#: How a resolved physical attempt reads to those who saw it.
_OUTCOME_WORDS = {
    "success": "it works",
    "partial": "it half works",
    "failure": "it does not work",
    "impossible": "it cannot be done",
}

#: Reactions that say nothing worth remembering ("Ash waits").
_SILENT_REPLIES = frozenset({ActionFamily.WAIT, ActionFamily.OBSERVE, ActionFamily.REST})


def choose_reactors(
    attempt_id: UUID, eligible: list[UUID], target: UUID | None, bystanders: int | None
) -> list[UUID]:
    """Who answers an attempt: everyone present, or (with a bystander cap)
    the person it is aimed at plus at most ``bystanders`` others.

    Bystanders are picked by a hash of (attempt, person): deterministic for
    a replayed beat, and spread across a crowd from one attempt to the next.
    Kept in scene order either way.
    """
    if bystanders is None or len(eligible) <= bystanders + (1 if target in eligible else 0):
        return eligible
    others = [c for c in eligible if c != target]
    picked = set(
        sorted(
            others,
            key=lambda c: hashlib.blake2b(attempt_id.bytes + c.bytes, digest_size=8).digest(),
        )[:bystanders]
    )
    return [c for c in eligible if c == target or c in picked]


def _reply_summary(action: ActionIntent, names: Mapping[UUID, str], reactor: UUID) -> str:
    """One-line reply text: speech reads as a reply, other acts as attempts."""
    if isinstance(action, CommunicateAction):
        who = names.get(reactor, "?")
        target = names.get(action.target_character_id, "?")
        return f"{who} replies to {target}: {action.topic}"
    return _summarize(action, names, reactor)


def _summarize(
    action: ActionIntent, names: Mapping[UUID, str], author_id: UUID | None = None
) -> str:
    """One-line attempt text; falls back to the author when the model
    returns a mismatched character_id (tolerated since S2, never fatal)."""
    fallback = names.get(author_id, "?") if author_id is not None else "?"
    who = names.get(action.character_id, fallback)
    if isinstance(action, MoveAction):
        return f"{who} goes to {names.get(action.destination_location_id, 'another place')}"
    if isinstance(action, CommunicateAction):
        target = names.get(action.target_character_id, "?")
        return f"{who} says to {target}: {action.topic}"
    if isinstance(action, SparAction):
        target = names.get(action.target_character_id, "?")
        weapon = f" with {action.weapon}" if action.weapon else ""
        return f"{who} spars with {target}{weapon}"
    if isinstance(action, AppealAction):
        return f"{who} appeals: {action.proposition}"
    if isinstance(action, TransferAction):
        target = names.get(action.target_character_id, "?")
        return f"{who} gives {target} {names.get(action.item_instance_id, 'an item')}"
    if isinstance(action, TakeAction):
        return f"{who} picks up {names.get(action.item_instance_id, 'something')}"
    if isinstance(action, InteractAction):
        return f"{who} tries to {action.attempt.strip().rstrip('.')}"
    family = action.family.value
    return f"{who} {family}s"


class Stage1Orchestrator:
    """Autonomous three-phase driver over the bounded Stage 1 graphs."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        canonical: CanonicalTransaction,
        tasks: TaskService,
        traces: TraceService,
        gateway_factory: GatewayFactory,
        profiles: Mapping[str, object],
        fault_hook: Callable[[str], None] | None = None,
        pin_gateway_factory: PinGatewayFactory | None = None,
        local_models: LocalModels | None = None,
        narration: BackgroundNarration | None = None,
        paint_moments: bool = False,
        moment_writer: Writer | None = None,
        max_parallel_calls: int = 12,
        reacting_bystanders: int | None = None,
    ) -> None:
        self._factory = uow_factory
        #: Crowd cap on who answers an attempt (None: everyone present).
        self._reacting_bystanders = reacting_bystanders
        #: Model-backed tasks (decisions, reactions, summaries) a beat runs at
        #: once, per event loop; see _bounded.
        self._max_parallel = max_parallel_calls
        #: Character cards read this beat (an orchestrator serves one beat).
        self._cards: CardCache = {}
        self._slots: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
            weakref.WeakKeyDictionary()
        )
        #: When set, a beat returns once its scenes commit and narration
        #: finishes behind it (party scenes still narrate in line).
        self._narration = narration
        #: Queue key-moment scene pictures (only with a live image service).
        self._paint_moments = paint_moments
        #: Reads a beat's narration for its picture (worth, headline, words).
        self._moment_writer = moment_writer
        #: Embeddings for recall by relevance; None keeps recency and salience only.
        self._local_models = local_models
        self._canonical = canonical
        self._tasks = tasks
        self._traces = traces
        self._gateways = gateway_factory
        self._profiles = dict(profiles)
        self._pin_gateways = pin_gateway_factory
        self._hook = fault_hook
        self._dnd_data: DataTables | None = None

    async def _bounded[T](self, work: Awaitable[T]) -> T:
        """Run one model-backed task within the beat's parallel-call budget.

        Each task reads its context from the database, so an unbounded burst
        (every decision, every attempt-reactor pair) queues on the connection
        pool; a large cast timed the pool out. Bounded tasks never nest.
        """
        loop = asyncio.get_running_loop()
        slot = self._slots.get(loop)
        if slot is None:
            slot = self._slots[loop] = asyncio.Semaphore(self._max_parallel)
        async with slot:
            return await work

    def _fire(self, point: str) -> None:
        if self._hook is not None:
            self._hook(point)

    async def _runtime(self, world_id: UUID) -> PhaseRuntime:
        """Resolve sampling plus gateway selection once per phase run."""
        async with self._factory() as uow:
            pin = await resolve_pin(uow, world_id)
            words = await uow.story_prompts.get(world_id)
        sampling = sampling_from_pin(pin) if pin is not None else SamplingParams()
        gateways: dict[str, ModelGateway] = {}
        profiles: dict[str, ModelProfile] = {}
        if pin is None:
            for role, profile in self._profiles.items():
                gateways[role] = self._gateways(role)
                profiles[role] = cast(ModelProfile, profile)
            gateways = frame_gateways(gateways, words.llm_prefix, words.llm_suffix)
            return PhaseRuntime(sampling=sampling, gateways=gateways, profiles=profiles, pin=None)
        if self._pin_gateways is None:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "story pins a provider profile the runtime cannot select",
                {"profile_id": str(pin.profile.id)},
            )
        for role in self._profiles:
            gateway = self._pin_gateways(role, pin)
            gateways[role] = gateway
            profiles[role] = gateway.profile
        gateways = frame_gateways(gateways, words.llm_prefix, words.llm_suffix)
        return PhaseRuntime(sampling=sampling, gateways=gateways, profiles=profiles, pin=pin)

    async def _open_wanted_place(
        self, world_id: UUID, player_intents: Mapping[UUID, ActionIntent] | None
    ) -> None:
        """Open a place people keep naming once someone sets out for it.

        Playtest: everyone talked of the mill road, Wren agreed to walk
        there, the player set out, and nobody could go: the director saw
        "mill road (4 mentions)" and chose to wait. A place mentioned at
        least OPEN_PLACE_MENTIONS times that the player's action this beat,
        or someone's intention, heads for now opens beside them, so the
        move can happen in the same beat. Within the story's place budget.
        """
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
            added = config.get(ADDED_PLACES_CONFIG_KEY)
            if (added if isinstance(added, int) else 0) >= MAX_ADDED_PLACES:
                return
            locations = await uow.locations.list_for_world(world_id)
            characters = await uow.characters.list_for_world(world_id)
            hooks = await uow.narrative.list_hooks_for_world(world_id)
            _recent, _quiet, _talk, said = await _recent_happenings(uow, world_id, with_lines=False)
            intentions = {
                c.id: i.text
                for c in characters
                if (i := await uow.intentions.get(c.id)) is not None
            }
        attempts = {
            cid: action.attempt
            for cid, action in (player_intents or {}).items()
            if isinstance(action, InteractAction)
        }
        # The player's own words first, then what characters mean to do.
        wanting = [*attempts.items(), *intentions.items()]
        if not wanting:
            return
        known = [loc.name for loc in locations] + sorted(
            {loc.region for loc in locations if loc.region}
        )
        people = [c.name for c in characters]
        talk = [*said, *intentions.values(), *(h.purpose for h in hooks), *attempts.values()]
        read: dict[str, list[str]] | None = None
        if self._local_models is not None:
            async with self._factory() as uow:
                read = await uow.mentions.places_for(MENTION_MODEL, talk)
        counts = {
            name.lower(): count
            for name, count in unmapped_places(talk, known, limit=20, read=read, people=people)
        }
        where = {c.id: c.location_id for c in characters}
        for character_id, text in wanting:
            for phrase, _n in unmapped_places([text], known, limit=3, read=read, people=people):
                if counts.get(phrase.lower(), 0) < OPEN_PLACE_MENTIONS:
                    continue
                origin = where.get(character_id)
                if origin is None:
                    continue
                name = " ".join(w if w.endswith("'s") else w.capitalize() for w in phrase.split())
                place = AddedPlace(
                    id=uuid5(world_id, f"opened:{phrase.lower()}"),
                    name=name,
                    connect_to=origin,
                    travel_phases=1,
                )
                async with self._factory() as uow:
                    await open_place(uow, world_id, place)
                    await uow.commit()
                _phase_log.info(
                    "opened %s for %s (%d mentions)", name, character_id, counts[phrase.lower()]
                )
                return

    async def _ground_player_moves(
        self, world_id: UUID, player_intents: Mapping[UUID, ActionIntent] | None
    ) -> Mapping[UUID, ActionIntent] | None:
        """A player's "Do" that plainly heads to a neighbouring place becomes the move."""
        if not player_intents or not any(
            isinstance(a, InteractAction) for a in player_intents.values()
        ):
            return player_intents
        async with self._factory() as uow:
            places = {loc.id: loc for loc in await uow.locations.list_for_world(world_id)}
            grounded: dict[UUID, ActionIntent] = {}
            for character_id, action in player_intents.items():
                if isinstance(action, InteractAction):
                    actor = await uow.characters.get(character_id)
                    here = places.get(actor.location_id)
                    reachable = {
                        route.destination_location_id: places[route.destination_location_id].name
                        for route in (here.routes if here is not None else [])
                        if route.destination_location_id in places
                    }
                    action = grounded_move(action, reachable) or action
                grounded[character_id] = action
        return grounded

    async def advance_phase(
        self,
        world_id: UUID,
        index: int,
        player_intents: Mapping[UUID, ActionIntent] | None = None,
        drain_queue: bool = False,
        submitter_id: UUID | None = None,
    ) -> Stage1PhaseReport:
        """Advance one phase end to end (manual advancement unit)."""
        await self._tasks.reconcile()
        if self._narration is not None:
            # The last beat's words first: beats never overlap, and the
            # recap and decisions read what was just narrated.
            await self._narration.settle(world_id)
        run_id = derive_run_id(world_id, index)
        async with self._factory() as uow:
            try:
                run = await uow.phases.get_run(run_id)
            except DomainError:
                run = None
        if run is not None and run.state.value == PhaseRunState.COMPLETED.value:
            return await self._duplicate_report(world_id, run_id)
        if run is not None and run.state.value in _BLOCKED_RUN_STATES:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"phase run is {run.state.value}; resume before advancing",
            )
        # Preflight before admission: a broken pin or a down provider
        # raises before any run row exists, so a rejected fresh advance
        # leaves no orphan open run and the same index can retry.
        runtime = await self._runtime(world_id)
        timings: dict[str, int] = {}
        phase_started = time.monotonic()
        self._fire("before_probe")
        with _timed(timings, "probe"):
            await self._probe_gate(runtime)
        await self._open_wanted_place(world_id, player_intents)
        player_intents = await self._ground_player_moves(world_id, player_intents)
        if self._narration is not None and index > 0:
            await self._narrate_leftovers(world_id, derive_run_id(world_id, index - 1), runtime)
        run, admitted_owner, admitted_role = await self._admit_run(
            world_id, index, player_intents, submitter_id
        )
        runtime = replace(runtime, controlled_character_id=admitted_owner)
        if run.state.value == PhaseRunState.COMPLETED.value:
            return await self._duplicate_report(world_id, run_id)
        await self._tick(world_id, run_id, index)
        sealed = await self._seal(world_id, run_id, index)

        # Decisions share one read of the world (phase_reads) until the
        # director, running beside them, finishes and may have changed it.
        decide_reads = phase_reads.PhaseReads()

        async def _directing() -> None:
            try:
                with _timed(timings, "director"):
                    await self._director_phase(world_id, run_id, index, sealed, runtime)
            finally:
                decide_reads.drop()

        # The director (every third beat, 1-7 s) runs beside the decisions:
        # characters decide from the sealed snapshot either way, and what
        # it adds (a rumour, a place, a newcomer) is there for the scenes
        # and for the next beat. It finishes before intents are recorded.
        director = asyncio.ensure_future(_directing())
        try:
            with phase_reads.sharing(decide_reads):
                intents = await self._drain_and_decide(
                    world_id,
                    run_id,
                    index,
                    sealed,
                    player_intents,
                    drain_queue=drain_queue,
                    runtime=runtime,
                    submitter_id=submitter_id,
                    grant_role=admitted_role,
                    timings=timings,
                )
        except BaseException as exc:
            # Cancelled (the caller went away): stop the director too, or
            # this await waits on a model call nobody is listening for.
            # asyncio delivers a cancel once; under anyio it used to repeat.
            if isinstance(exc, asyncio.CancelledError):
                director.cancel()
            with contextlib.suppress(BaseException):
                await director
            raise
        await director
        await self._set_state(run_id, PhaseRunState.INTENTS_COMPLETE)
        quiet = is_quiet_phase(intent.action.family for intent in intents)
        async with self._factory() as uow:
            characters = [
                c for c in await uow.characters.list_for_world(world_id) if c.id in sealed.locations
            ]
            locations = await uow.locations.list_for_world(world_id)
            live_world = await uow.worlds.get(world_id)
        # Place names ride along so attempts read "Wren goes to the Market".
        async with self._factory() as uow:
            world_items = await uow.inventory.list_for_world(world_id)
        names = (
            {c.id: c.name for c in characters}
            | {loc.id: loc.name for loc in locations}
            | {i.id: item_label(i) for i in world_items}
        )
        # Simultaneous decisions: two characters heading for each other
        # would swap places; one waits so they meet.
        # Models name a destination, never a route id: fill the route from
        # where each character stands, or every autonomous move fails.
        places = {loc.id: loc for loc in locations}
        intents = [
            i.model_copy(
                update={
                    "action": with_route(
                        i.action, sealed.locations.get(i.author_character_id), places
                    )
                }
            )
            for i in intents
        ]
        intents = resolve_meetups(intents, sealed.locations, names)
        view = WorldView(world=live_world, characters=characters, locations=locations)
        scenes = assemble_scenes(
            intents,
            view,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
        )
        await self._set_state(run_id, PhaseRunState.SCENES_ASSEMBLED)
        outcomes: list[SceneOutcome] = []
        budgets: list[bool] = []
        #: Narration still being written behind the beat, if any.
        narrated: asyncio.Future[Any] | None = None
        with _timed(timings, "scenes"):
            # Scenes commit one after another (event sequence numbers and
            # version checks are ordered); their narration, written after
            # the commits and reading only, then runs for all scenes at once.
            # Party scenes run one at a time: their narration applies combat
            # and recruit tags (monsters, hit points), not safe side by side.
            async with self._factory() as uow:
                party = bool(await uow.party.list_for_world(world_id))
            budgets = [await self._over_budget(world_id, run_id) for _scene in scenes]
            if party or len(scenes) < 2:
                for scene in scenes:
                    outcomes.append(
                        await self._commit_scene(
                            world_id,
                            run_id,
                            index,
                            sealed,
                            scene,
                            intents,
                            names,
                            runtime=runtime,
                            timings=timings,
                            narrate=False,
                        )
                    )
            else:
                # A beat's scenes hold different people at different places:
                # their model work (reactions, resolution) runs side by side;
                # the commits stay in order (event sequence, version checks).
                # Preparing only reads, so all of it shares one world read.
                with phase_reads.sharing(phase_reads.PhaseReads()):
                    prepared = await asyncio.gather(
                        *(
                            self._prepare_scene(
                                world_id,
                                run_id,
                                sealed,
                                scene,
                                intents,
                                names,
                                runtime=runtime,
                                timings=timings,
                            )
                            for scene in scenes
                        )
                    )
                for scene, ready in zip(scenes, prepared, strict=True):
                    try:
                        outcomes.append(
                            await self._commit_prepared(
                                world_id, run_id, index, sealed, scene, ready
                            )
                        )
                    except DomainError as exc:
                        if exc.code is not ErrorCode.VERSION_CONFLICT:
                            raise
                        # An earlier scene touched the same thing: redo this
                        # one against the world as it now stands.
                        outcomes.append(
                            await self._commit_scene(
                                world_id,
                                run_id,
                                index,
                                sealed,
                                scene,
                                intents,
                                names,
                                runtime=runtime,
                                timings=timings,
                                narrate=False,
                            )
                        )
            self._fire("before_narration")
            jobs = [
                self._narrate_outcome(world_id, run_id, scene, outcome, quiet, budget, runtime)
                for scene, outcome, budget in zip(scenes, outcomes, budgets, strict=True)
            ]
            with _timed(timings, "narrate"):
                if party:
                    outcomes = [await job for job in jobs]
                elif self._narration is not None:
                    narrated = self._narration.start(world_id, asyncio.gather(*jobs))
                    outcomes = [replace(o, narration="pending") for o in outcomes]
                else:
                    outcomes = list(await asyncio.gather(*jobs))
        await self._set_state(run_id, PhaseRunState.SCENES_COMMITTED)
        self._fire("after_scenes_committed")
        await self._set_state(run_id, PhaseRunState.COMPLETED)
        player = runtime.controlled_character_id
        # Watched stories (no player) get key moments too (watched-moments-001).
        if self._paint_moments and outcomes:
            # The moment is read from the narration, so it waits for it;
            # behind the beat when narration is, keeping turns quick.
            paint = self._queue_moment(
                world_id, index, player, [o.scene_id for o in outcomes], narrated
            )
            if self._narration is not None:
                self._narration.start(world_id, paint)
            else:
                with _timed(timings, "moments"):
                    await paint
        if index % PHASES_PER_DAY == PHASES_PER_DAY - 1:

            async def _day_end() -> None:
                day = index // PHASES_PER_DAY + 1
                try:
                    await self._summarize_day(world_id, run_id, index, day, runtime)
                    await self._promote_memories(world_id, run_id, index, day, runtime)
                finally:
                    # The day's summaries and the salience they bump belong
                    # to the turn that ended the day: keep it after them.
                    await self._keep_turn(world_id, index)

            if self._narration is not None:
                # Midnight turns took 26-36 s with this inline; the next
                # beat waits for it, as it does for narration.
                self._narration.start(world_id, _day_end())
            else:
                with _timed(timings, "day_end"):
                    await _day_end()
        else:
            with _timed(timings, "checkpoint"):
                await self._keep_turn(world_id, index)
        timings["total"] = int((time.monotonic() - phase_started) * 1000)
        _phase_log.info(
            "phase %s timings %s",
            index,
            timings,
            extra={"world_id": str(world_id), "phase_index": index, "timings_ms": timings},
        )
        return Stage1PhaseReport(
            run_id=run_id,
            world_id=world_id,
            absolute_index=index,
            snapshot_id=sealed.snapshot_id,
            scenes=outcomes,
            quiet=quiet,
            timings_ms=timings,
        )

    async def _keep_turn(self, world_id: UUID, index: int) -> None:
        """Keep the story's state at this turn's end, so it can branch from it.

        At a safe boundary: the turn's scenes are committed and the next
        beat waits for this. A failure is logged, never raised: the turn
        stands, it just can't be branched from.
        """
        try:
            async with self._factory() as uow:
                size = await uow.checkpoints.capture(world_id, index)
                await uow.commit()
            _phase_log.debug(
                "turn kept", extra={"world_id": str(world_id), "phase_index": index, "bytes": size}
            )
        except Exception:
            _phase_log.exception(
                "keeping a turn for branching failed",
                extra={"world_id": str(world_id), "phase_index": index},
            )
            return
        # Retention (rewind-001): the newest turns, and the last turn of each
        # older day. Its own transaction: a failure keeps a few extra rows.
        try:
            async with self._factory() as uow:
                await uow.checkpoints.prune(world_id, index)
                await uow.commit()
        except Exception:
            _phase_log.exception(
                "pruning kept turns failed",
                extra={"world_id": str(world_id), "phase_index": index},
            )

    async def _queue_moment(
        self,
        world_id: UUID,
        index: int,
        player: UUID | None,
        scene_ids: list[UUID],
        narrated: asyncio.Future[Any] | None = None,
    ) -> None:
        """Queue a picture of this beat's key moment, if it had one.

        Once the narration is written, the moment writer (when there is
        one) reads the player's first narrated scene: worth, headline,
        caption and what to paint. Pictures are decoration: a failure
        here is logged, never raised, so a turn always completes.
        """
        try:
            if narrated is not None:
                await asyncio.wait([narrated])
            async with self._factory() as uow:
                prefs = (await uow.settings.get_preferences(LOCAL_OPERATOR)).images
                if not (prefs.enabled and prefs.scene_moments):
                    return
                scenes = [await uow.scenes.get_scene(scene_id) for scene_id in scene_ids]
                plans = await plan_moments(uow, player, scenes)
            words: dict[UUID, MomentWords] = {}
            told = [plan for plan in plans if plan.narration.strip()]
            # The player's first scene; in a watched story the longest few
            # (one writer call each, about $0.0001), the most worthwhile first.
            judged = (
                told[:1]
                if player is not None
                else sorted(told, key=lambda p: len(p.narration), reverse=True)[
                    :WATCHED_SCENES_JUDGED
                ]
            )
            if self._moment_writer is not None:
                for plan in judged:
                    said, cost = await judge_moment(self._moment_writer, plan)
                    if said is not None:
                        words[plan.scene.id] = said
                    _phase_log.info(
                        "moment judged",
                        extra={
                            "world_id": str(world_id),
                            "worth": said.worth if said else None,
                            "cost_usd": cost,
                        },
                    )
            if player is None:
                plans = sorted(
                    plans,
                    key=lambda p: words[p.scene.id].worth if p.scene.id in words else -1,
                    reverse=True,
                )
            async with self._factory() as uow:
                style_pack = await world_style_pack(uow, world_id)
                if await queue_moment(uow, world_id, index, player, plans, style_pack, words):
                    await uow.commit()
        except Exception:
            _phase_log.exception(
                "queueing a moment picture failed", extra={"world_id": str(world_id)}
            )

    async def _narrate_leftovers(self, world_id: UUID, run_id: UUID, runtime: PhaseRuntime) -> None:
        """Narrate committed scenes of an earlier beat still without words.

        Background narration that a stopped process never finished; each
        scene narrates at most once, so this is safe to repeat.
        """
        async with self._factory() as uow:
            scenes = [
                s
                for s in await uow.scenes.list_for_run(run_id)
                if s.event_id is not None and s.narration_status is None
            ]
        for scene in scenes:
            assert scene.event_id is not None
            await self._narrate_scene(world_id, run_id, scene, scene.event_id, runtime=runtime)

    async def _drain_and_decide(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        sealed: SealedPhase,
        player_intents: Mapping[UUID, ActionIntent] | None,
        *,
        drain_queue: bool,
        runtime: PhaseRuntime,
        submitter_id: UUID | None,
        grant_role: UserRole | None,
        timings: dict[str, int],
    ) -> list[Intent]:
        """Drain queued directions, then decide for every character.

        Queued directions drain inside the beat (past the duplicate replay):
        effects apply pre-decision, attempts merge into the decision and
        complete only once their scenes commit.
        """
        directed: dict[UUID, tuple[ActionIntent, str]] = {}
        if drain_queue:
            batch = await claim_for_boundary(self._factory, world_id, f"s1:{run_id.hex[:8]}")
            await apply_batch(self._factory, world_id, index, batch, set(player_intents or {}))
            # Conditions created by this drain tick in their start phase too;
            # the route ticks before the beat, when they do not exist yet.
            # Idempotent per (condition, index), so existing ones tick once.
            await tick_conditions(self._factory, world_id, index)
            for planned in await plan_attempts(
                self._factory, world_id, sealed.snapshot_id, set(player_intents or {})
            ):
                directed[planned.actor] = (planned.intent, planned.ref)
        merged = dict(player_intents or {})
        merged.update({actor: intent for actor, (intent, _ref) in directed.items()})
        with _timed(timings, "decide"):
            intents = await self._decide_all(
                world_id,
                run_id,
                sealed,
                merged,
                directed,
                runtime=runtime,
                submitter_id=submitter_id,
                grant_role=grant_role,
            )
        return intents

    async def _over_budget(self, world_id: UUID, run_id: UUID) -> bool:
        """True when this run already spent its model-call budget."""
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
            spent = len(await uow.traces.list_for_phase_run(run_id))
        raw = config.get("model.max_calls_per_phase")
        budget = int(raw) if isinstance(raw, int) else 32
        return spent >= max(1, budget)

    async def advance_days(
        self,
        world_id: UUID,
        start_index: int,
        day_count: int,
        player_intents: Mapping[int, Mapping[UUID, ActionIntent]] | None = None,
    ) -> list[Stage1PhaseReport]:
        """Advance whole days (ten phases each) for soak scenarios."""
        reports: list[Stage1PhaseReport] = []
        for offset in range(day_count * PHASES_PER_DAY):
            index = start_index + offset
            intents = (player_intents or {}).get(index)
            reports.append(await self.advance_phase(world_id, index, intents))
        return reports

    async def advance_three_phases(
        self,
        world_id: UUID,
        start_index: int,
        player_intents: Mapping[int, Mapping[UUID, ActionIntent]] | None = None,
    ) -> list[Stage1PhaseReport]:
        """Automatic advancement across three consecutive phases."""
        reports: list[Stage1PhaseReport] = []
        for offset in range(3):
            index = start_index + offset
            phase_players = (player_intents or {}).get(index, {})
            reports.append(await self.advance_phase(world_id, index, phase_players))
        return reports

    async def pause_phase(self, run_id: UUID) -> None:
        await self._set_state(run_id, PhaseRunState.PAUSED)

    async def resume_phase(self, run_id: UUID) -> None:
        await self._set_state(run_id, PhaseRunState.CREATED)

    async def _set_state(self, run_id: UUID, state: PhaseRunState) -> None:
        async with self._factory() as uow:
            await uow.phases.set_run_state(run_id, state.value)
            await uow.commit()

    async def _probe_gate(self, runtime: PhaseRuntime) -> None:
        roles = ("character", "reaction", "resolver", "narrator")
        # Concurrent: each probe is an independent provider round trip.
        probes = await asyncio.gather(*(runtime.gateways[role].probe() for role in roles))
        for role, probe in zip(roles, probes, strict=True):
            if not probe.ok:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"provider unavailable for {role}: {probe.detail}",
                )

    async def _admit_run(
        self,
        world_id: UUID,
        index: int,
        player_intents: Mapping[UUID, ActionIntent] | None = None,
        submitter_id: UUID | None = None,
    ) -> tuple[PhaseRun, UUID | None, UserRole | None]:
        """Create-or-resume one phase run under a per-world admission lock.

        One transaction holds the world row locked while it validates
        the clock and the previous run, refuses a different open run,
        resolves the active role grant (presence and role), rejects
        submissions that no longer match it, and creates this index run.
        The grant is captured inside the same transaction, after provider
        preflight and before the commit, so a grant change racing
        preflight cannot leak stale ownership or a stale submission into
        the beat; the admitted owner is frozen for the run. Same-run
        replay resumes via a pre-read under the lock (role changes are
        refused while any run is open, so the re-read is stable); only
        a twin commit of this exact run is tolerated, verified by
        identity-matching re-read, and every other integrity failure
        raises. No model calls happen inside.
        """
        run_id = derive_run_id(world_id, index)
        self._fire("before_admission")
        try:
            async with self._factory() as uow:
                world = await uow.worlds.lock(world_id)
                current = absolute_index(world.day, world.phase)
                if current + 1 != index and current != index:
                    raise DomainError(
                        ErrorCode.VALIDATION_FAILED,
                        f"phases advance consecutively: clock={current} target={index}",
                    )
                await self._require_previous_complete_in(uow, world_id, index)
                open_run = await uow.phases.find_open_run(world_id)
                if open_run is not None and open_run.id != run_id:
                    raise DomainError(
                        ErrorCode.PRECONDITION_FAILED,
                        f"phase run {open_run.id} is still open; reconcile or resume it "
                        "before advancing another index",
                        {"open_run_id": str(open_run.id), "run_id": str(run_id)},
                    )
                try:
                    existing = await uow.phases.get_run(run_id)
                except DomainError:
                    existing = None
                owner = await resolve_controlled_character(uow, world_id)
                grant = await uow.roles.get_for_world(world_id)
                grant_role = grant.role if grant is not None else None
                self._reject_stale_submissions(owner, player_intents, submitter_id, grant_role)
                if existing is not None:
                    return existing, owner, grant_role
                await uow.phases.create_run(
                    PhaseRun(id=run_id, world_id=world_id, absolute_index=index)
                )
                await uow.commit()
                admitted = await uow.phases.get_run(run_id)
                return admitted, owner, grant_role
        except IntegrityError as exc:
            # Only a twin insert of this exact run can reach here: the
            # pre-read above runs under the same world lock, so any
            # other constraint failure finds no such row and re-raises.
            async with self._factory() as uow:
                try:
                    twin = await uow.phases.get_run(run_id)
                except DomainError:
                    raise exc from None
                if twin.world_id != world_id or twin.absolute_index != index:
                    raise exc from None
                await uow.worlds.lock(world_id)
                twin_owner = await resolve_controlled_character(uow, world_id)
                twin_grant = await uow.roles.get_for_world(world_id)
                twin_role = twin_grant.role if twin_grant is not None else None
                self._reject_stale_submissions(twin_owner, player_intents, submitter_id, twin_role)
                return twin, twin_owner, twin_role

    @staticmethod
    def _reject_stale_submissions(
        owner: UUID | None,
        player_intents: Mapping[UUID, ActionIntent] | None,
        submitter_id: UUID | None = None,
        grant_role: UserRole | None = None,
    ) -> None:
        """Refuse player submissions that no longer match the authorization.

        Submissions carry the request-time authorization (which actor each
        action was filed for, plus who filed them), but provider preflight
        runs before admission; a grant change inside that window must not
        let a stale action commit. The admitted grant presence and role
        decide: an active player grant admits only its bound character;
        an active Watcher/Director/Deity grant admits no player action;
        with no grant, only the request-time authorized submitter (header
        player) may file. Directed and system execution paths never flow
        through player_intents, so they are unaffected. Rejection happens
        before any run row is created, leaving no orphan open run.
        """
        if not player_intents:
            return
        if grant_role == UserRole.PLAYER:
            stale = [actor for actor in player_intents if actor != owner]
            if not stale:
                return
            if owner is None:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "player submission is stale: no player currently controls a character",
                )
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "player submission is stale: the active grant now controls "
                f"{owner}, not {stale[0]}",
                {
                    "controlled_character_id": str(owner),
                    "stale_actor_id": str(stale[0]),
                },
            )
        if grant_role is None:
            if submitter_id is None or any(actor != submitter_id for actor in player_intents):
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "player submission is stale: no player currently controls a character",
                )
            return
        raise DomainError(
            ErrorCode.FORBIDDEN,
            f"player submissions are forbidden under the active {grant_role.value} grant",
            {"role": grant_role.value},
        )

    async def _require_previous_complete_in(
        self, uow: UnitOfWork, world_id: UUID, index: int
    ) -> None:
        """Refuse a new phase while the prior run is not completed.

        Same-transaction variant for admission: shares the world-row
        lock so the previous run cannot change mid-check.
        """
        if index <= 1:
            return
        previous_id = derive_run_id(world_id, index - 1)
        try:
            previous = await uow.phases.get_run(previous_id)
        except DomainError:
            # A completed macro run ending exactly here covers every prior
            # phase; detailed simulation resumes at the macro clock.
            covered = await uow.macro.find_covering_run(world_id, index)
            if covered is None:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"previous phase {index - 1} never ran; advance consecutively",
                ) from None
            return
        if previous.state.value != PhaseRunState.COMPLETED.value:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"previous phase {index - 1} is {previous.state.value}; reconcile first",
            )

    async def _fire_due_schedules(self, world_id: UUID, index: int) -> int:
        """Record one event per due schedule; applied rows never refire."""
        async with self._factory() as uow:
            due = await uow.schedules.list_due(world_id, index)
            for schedule in due:
                sequence = await uow.events.max_sequence(world_id) + 1
                await uow.events.append_event(
                    WorldEvent(
                        id=schedule.id,
                        world_id=world_id,
                        sequence=sequence,
                        event_type=EventType.SCHEDULE_FIRED,
                        absolute_index=index,
                        phase_run_id=derive_run_id(world_id, index),
                        participant_ids=[],
                        summary={
                            "kind": schedule.kind,
                            "due": str(schedule.due_absolute),
                        },
                    )
                )
                await uow.schedules.save(
                    schedule.model_copy(update={"status": ScheduleStatus.APPLIED}),
                    schedule.version,
                )
            await uow.commit()
            return len(due)

    async def _tick(self, world_id: UUID, run_id: UUID, index: int) -> None:
        async with self._factory() as uow:
            world = await uow.worlds.get(world_id)
            version = await uow.versions.get(world_id) or 0
        if absolute_index(world.day, world.phase) == index:
            await self._set_state(run_id, PhaseRunState.WORLD_TICKED)
            await self._fire_due_schedules(world_id, index)
            await self._advance_activities(world_id, run_id, index)
            return
        effect = AdvanceClockEffect(
            affected_ids=[world_id],
            expected_versions={str(world_id): version},
            from_index=absolute_index(world.day, world.phase),
            to_index=index,
        )
        key = f"phase_tick:{world_id.hex}:{index}"
        payload: dict[str, object] = {"absolute_index": index}
        await self._canonical.commit(
            CommitRequest(
                command_id=uuid4(),
                world_id=world_id,
                idempotency_key=key,
                actor_role="system",
                command_type="advance_phase",
                expected_versions={str(world_id): version},
                payload=payload,
                input_hash=canonical_input_hash(
                    {"key": key, "payload": payload, "effects": [effect.model_dump(mode="json")]}
                ),
                absolute_index=index,
                phase_run_id=run_id,
                event_type=EventType.WORLD_TICKED,
                effects=[effect],
            )
        )
        await self._set_state(run_id, PhaseRunState.WORLD_TICKED)
        await self._fire_due_schedules(world_id, index)
        await self._advance_activities(world_id, run_id, index)

    async def _advance_activities(self, world_id: UUID, run_id: UUID, index: int) -> int:
        """Progress due activities; completion commits once per activity.

        Progress is derived from the clock, so this only writes when an
        activity finishes. Exhausted travelers stall instead of moving.
        """
        async with self._factory() as uow:
            due = [
                activity
                for activity in await uow.activities.list_active_for_world(world_id)
                if effective_progress(activity, index) >= activity.duration_phases
            ]
        completed = 0
        for activity in due:
            if await self._complete_activity(world_id, run_id, index, activity):
                completed += 1
        return completed

    async def _complete_activity(
        self, world_id: UUID, run_id: UUID, index: int, activity: Activity
    ) -> bool:
        """Commit one activity's completion effects, then mark it done."""
        async with self._factory() as uow:
            character = await uow.characters.get(activity.character_id)
        effects: list[DomainEffect] = []
        observations: list[ObservationSpec] = []
        participants: list[UUID] = []
        summary: dict[str, str] = {}
        try:
            if activity.kind == ActivityKind.TRAVEL:
                destination = UUID(str(activity.payload["to_location_id"]))
                cost = int(activity.payload.get("stamina_cost", 0))
                # The arrival is the traveller's own event: the chronicle and
                # their memory say where they got to.
                participants = [character.id]
                summary = {"location_id": str(destination), "arrival": "1"}
                async with self._factory() as uow:
                    there = await uow.locations.get(destination)
                observations.append(
                    ObservationSpec(
                        observer_id=character.id,
                        facts=[
                            ObservationFact(
                                key=f"arrival:{there.name}",
                                value=(
                                    f"arrived after {activity.duration_phases} phases on the road"
                                ),
                            )
                        ],
                    )
                )
                effects.append(
                    MoveEntityEffect(
                        affected_ids=[character.id],
                        expected_versions={str(character.id): character.version},
                        from_location_id=character.location_id,
                        to_location_id=destination,
                    )
                )
                remaining = spend(character.stamina, cost)
                if remaining != character.stamina:
                    effects.append(
                        ResourceAdjustedEffect(
                            affected_ids=[character.id],
                            expected_versions={str(character.id): character.version},
                            resource=ResourceKind.STAMINA,
                            delta=remaining - character.stamina,
                        )
                    )
            elif activity.kind == ActivityKind.REST:
                stamina_gain, mana_gain = rest_recovery(activity.duration_phases)
                rested_stamina = restore(character.stamina, stamina_gain)
                if rested_stamina != character.stamina:
                    effects.append(
                        ResourceAdjustedEffect(
                            affected_ids=[character.id],
                            expected_versions={str(character.id): character.version},
                            resource=ResourceKind.STAMINA,
                            delta=rested_stamina - character.stamina,
                        )
                    )
                rested_mana = restore(character.mana, mana_gain)
                if rested_mana != character.mana:
                    effects.append(
                        ResourceAdjustedEffect(
                            affected_ids=[character.id],
                            expected_versions={str(character.id): character.version},
                            resource=ResourceKind.MANA,
                            delta=rested_mana - character.mana,
                        )
                    )
            elif activity.kind == ActivityKind.TRAIN:
                session = self._training_session_key(activity)
                assert session is not None
                if character.stamina < TRAINING_STAMINA_COST:
                    raise DomainError(ErrorCode.INSUFFICIENT_RESOURCE, "too tired to train")
                effects.append(
                    SkillProgressEffect(
                        affected_ids=[character.id],
                        expected_versions={str(character.id): character.version},
                        character_id=character.id,
                        skill_key=str(activity.payload.get("skill", "general")),
                        session_key=session,
                    )
                )
                effects.append(
                    ResourceAdjustedEffect(
                        affected_ids=[character.id],
                        expected_versions={str(character.id): character.version},
                        resource=ResourceKind.STAMINA,
                        delta=-TRAINING_STAMINA_COST,
                    )
                )
            elif activity.kind == ActivityKind.PATROL:
                async with self._factory() as uow:
                    origin = await uow.locations.get(character.location_id)
                observations.append(
                    ObservationSpec(
                        observer_id=character.id,
                        facts=[
                            ObservationFact(
                                key=f"patrol:{origin.name}",
                                value="quiet, no movement on the roads",
                            )
                        ],
                    )
                )
        except DomainError:
            await self._stall_activity(activity, index)
            return False
        key = f"activity_complete:{activity.id.hex}"
        try:
            await self._canonical.commit(
                CommitRequest(
                    command_id=uuid4(),
                    world_id=world_id,
                    idempotency_key=key,
                    actor_role="system",
                    command_type="complete_activity",
                    expected_versions={str(character.id): character.version},
                    payload={"activity_id": str(activity.id), "kind": activity.kind.value},
                    input_hash=canonical_input_hash(
                        {
                            "key": key,
                            "activity": str(activity.id),
                            "effects": [e.model_dump(mode="json") for e in effects],
                        }
                    ),
                    absolute_index=index,
                    phase_run_id=run_id,
                    event_type=EventType.ACTION_RESOLVED,
                    effects=effects,
                    observations=observations,
                    participant_ids=participants,
                    summary=summary,
                )
            )
        except IntegrityError:
            if not await self._session_awarded(
                world_id, activity, self._training_session_key(activity)
            ):
                raise
        async with self._factory() as uow:
            try:
                await uow.activities.save(
                    activity.model_copy(update={"status": ActivityStatus.COMPLETED}),
                    activity.version,
                )
                await uow.commit()
            except DomainError:
                pass
        return True

    def _training_session_key(self, activity: Activity) -> str | None:
        if activity.kind != ActivityKind.TRAIN:
            return None
        return f"activity:{activity.id.hex}:{activity.start_absolute}"

    async def _session_awarded(
        self, world_id: UUID, activity: Activity, session_key: str | None
    ) -> bool:
        if session_key is None:
            return False
        async with self._factory() as uow:
            return await uow.progress.has_session(
                world_id,
                activity.character_id,
                str(activity.payload.get("skill", "general")),
                session_key,
            )

    async def _stall_activity(self, activity: Activity, index: int) -> None:
        """Exhausted traveler: bake progress and freeze without moving."""
        async with self._factory() as uow:
            try:
                await uow.activities.save(
                    activity.model_copy(
                        update={
                            "status": ActivityStatus.INTERRUPTED,
                            "progress_phases": effective_progress(activity, index),
                        }
                    ),
                    activity.version,
                )
                await uow.commit()
            except DomainError:
                pass

    async def _summarize_day(
        self, world_id: UUID, run_id: UUID, index: int, day: int, runtime: PhaseRuntime
    ) -> int:
        """Record one versioned summary per owner with same-day sources.

        Runs after midnight commits and never fails the phase: each
        owner is attempted independently, and model trouble falls back
        to structural counts. Owners with no sources get no record.
        """
        start, end = day_range(day)
        async with self._factory() as uow:
            characters = [
                c
                for c in await uow.characters.list_for_world(world_id)
                if c.life_status == LifeStatus.ALIVE
            ]

        async def _one(character: Character) -> bool:
            try:
                return await self._summarize_owner(
                    world_id, run_id, character, day, start, end, runtime
                )
            except Exception:
                return False

        # Owners are independent (own sources, own task): side by side.
        done = await asyncio.gather(
            *(self._bounded(_one(c)) for c in sorted(characters, key=lambda c: c.id.hex))
        )
        return sum(done)

    async def _summarize_owner(
        self,
        world_id: UUID,
        run_id: UUID,
        character: Character,
        day: int,
        start: int,
        end: int,
        runtime: PhaseRuntime,
    ) -> bool:
        """Propose and store one owner's day account; False when sourceless."""
        async with self._factory() as uow:
            observations = [
                obs
                for obs in await uow.perception.observations_for_observer(character.id, 20)
                if start <= obs.created_phase_index <= end
            ]
            memories = [
                mem
                for mem in await uow.perception.memories_for_owner(character.id)
                if start <= mem.created_phase_index <= end
            ]
        if not observations and not memories:
            return False
        entries: list[tuple[str, str]] = []
        source_ids: list[str] = []
        for obs in observations:
            for fact in obs.facts:
                entries.append((f"obs:{obs.id}", f"{fact.key}: {fact.value}"))
                source_ids.append(f"obs:{obs.id}")
        for mem in memories:
            entries.append((f"mem:{mem.id}", mem.text))
            source_ids.append(f"mem:{mem.id}")
        # Short tags ([o1], [m2]) instead of full ids: the model echoed ~30
        # uuids per summary (~70% of its output) and dropped their prefixes.
        sources_text, tags = tag_sources(entries)
        task_run_id = derive_task_id(run_id, "summary", character.id)
        owner = f"s1sum:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        spec = ManifestSpec(
            role="daily_summary",
            profile=runtime.profiles["summary"],
            prompt_version=SUMMARY_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=character.id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
            pin_profile_id=runtime.pin_id,
            pin_profile_revision=runtime.pin_revision,
        )
        traced = TracedGateway(runtime.gateways["summary"], self._traces, spec)
        invocation = GraphInvocation(
            graph_name="daily-summary",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=run_id,
            actor_id=character.id,
            role="daily_summary",
            profile_version=traced.profile.version,
            prompt_version=SUMMARY_PROMPT_VERSION,
            input={
                "owner_name": character.name,
                "day": day,
                "sources_text": sources_text,
                "source_ids": accepted_ids(tags),
            },
        )
        sampling = runtime.sampling
        graph = build_summary_graph(
            SummaryGraphDeps(
                gateway=traced,
                profile=runtime.profiles["summary"],
                system_template=load_summary_prompt(),
                temperature=sampling.temperature,
                top_p=sampling.top_p,
                top_k=sampling.top_k,
                max_tokens=role_max_tokens(sampling.max_tokens, "summary"),
            )
        )
        try:
            result = await invoke(graph, invocation)
        except Exception:
            await self._finish_task(task_run_id, owner, False)
            return False
        await self._finish_task(task_run_id, owner, True)
        proposal: dict[str, Any] = result.get("proposal") or {}
        is_fallback = result.get("fallback", True) is True
        text = str(proposal.get("text", "")) or fallback_text(len(observations), len(memories))
        raw_cited: list[Any] = untag([str(s) for s in proposal.get("source_ids", [])], tags)
        cited = [str(s) for s in raw_cited] or sorted(set(source_ids))
        async with self._factory() as uow:
            taken = await uow.summaries.count_versions(world_id, character.id, day)
            await uow.summaries.add(
                DailySummary(
                    id=new_summary_id(),
                    world_id=world_id,
                    owner_id=character.id,
                    day=day,
                    text=text,
                    source_ids=cited,
                    profile_version=traced.profile.version,
                    prompt_version=SUMMARY_PROMPT_VERSION,
                    fallback=is_fallback or not proposal,
                    version=taken + 1,
                )
            )
            await self._bump_cited(uow, world_id, [str(s) for s in raw_cited])
            await uow.commit()
        return True

    async def _bump_cited(self, uow: Any, world_id: UUID, cited: list[str]) -> None:
        """Raise salience for model-cited sources only.

        Fallback-expanded citations (the whole same-day set) never
        bump: indiscriminate bumps would push every row to the cap
        within days and erase all discrimination.
        """
        if not cited:
            return
        config = await uow.worlds.get_config(world_id)
        raw_bump = config.get(CITE_BUMP_KEY)
        bump = float(raw_bump) if isinstance(raw_bump, (int, float)) else DEFAULT_CITE_BUMP
        obs_ids: list[UUID] = []
        mem_ids: list[UUID] = []
        for source_id in cited:
            kind, _, raw = source_id.partition(":")
            try:
                parsed = UUID(raw)
            except ValueError:
                continue
            if kind == "obs":
                obs_ids.append(parsed)
            elif kind == "mem":
                mem_ids.append(parsed)
        if obs_ids or mem_ids:
            await uow.perception.bump_salience(obs_ids, mem_ids, bump, MAX_SALIENCE)

    async def _promote_memories(
        self, world_id: UUID, run_id: UUID, index: int, day: int, runtime: PhaseRuntime
    ) -> int:
        """Compress qualifying old sources into digests; never fails the phase."""
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
        if config.get(PROMOTION_ENABLED_KEY, True) is False:
            return 0
        async with self._factory() as uow:
            characters = [
                c
                for c in await uow.characters.list_for_world(world_id)
                if c.life_status == LifeStatus.ALIVE
            ]
        written = 0
        for character in sorted(characters, key=lambda c: c.id.hex):
            try:
                if await self._promote_owner(
                    world_id, run_id, index, day, character, config, runtime
                ):
                    written += 1
            except Exception:
                continue
        return written

    async def _promote_owner(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        day: int,
        character: Character,
        config: dict[str, object],
        runtime: PhaseRuntime,
    ) -> bool:
        """Digest one owner's qualifying old sources; False when none qualify."""
        threshold = _config_float(config, PROMOTION_THRESHOLD_KEY, DEFAULT_PROMOTION_THRESHOLD)
        min_age = _config_int(config, PROMOTION_MIN_AGE_KEY, DEFAULT_PROMOTION_MIN_AGE)
        max_per_day = _config_int(config, PROMOTION_MAX_PER_DAY_KEY, DEFAULT_PROMOTION_MAX_PER_DAY)
        max_total = _config_int(config, PROMOTION_MAX_TOTAL_KEY, DEFAULT_PROMOTION_MAX_TOTAL)
        async with self._factory() as uow:
            taken = await uow.digests.count_versions(world_id, character.id, day)
            if taken >= max_per_day:
                return False
            owned = await uow.digests.list_for_owner(world_id, character.id)
            if len(owned) >= max_total:
                return False
            digested = {
                str(source)
                for digest in await uow.digests.list_for_owner(world_id, character.id)
                for source in digest.source_ids
            }
            # Only salient rows can be digested: let the database filter them
            # (this read every observation the character ever made).
            observations = await uow.perception.observations_for_observer(
                character.id, 100000, since_phase_index=index + 1, min_salience=threshold
            )
            memories = await uow.perception.memories_for_owner(
                character.id, since_phase_index=index + 1, min_salience=threshold
            )
        entries: list[tuple[str, str]] = []
        source_ids: list[str] = []
        for obs in observations:
            if obs.salience < threshold or index - obs.created_phase_index < min_age:
                continue
            if f"obs:{obs.id}" in digested:
                continue
            for fact in obs.facts:
                entries.append((f"obs:{obs.id}", f"{fact.key}: {fact.value}"))
                source_ids.append(f"obs:{obs.id}")
        for mem in memories:
            if mem.salience < threshold or index - mem.created_phase_index < min_age:
                continue
            if f"mem:{mem.id}" in digested:
                continue
            entries.append((f"mem:{mem.id}", mem.text))
            source_ids.append(f"mem:{mem.id}")
        if not entries:
            return False
        # Short tags ([o1], [m2]) instead of full ids: the model echoed ~30
        # uuids per summary (~70% of its output) and dropped their prefixes.
        sources_text, tags = tag_sources(entries)
        task_run_id = derive_task_id(run_id, "digest", character.id)
        owner = f"s1digest:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        spec = ManifestSpec(
            role="memory_digest",
            profile=runtime.profiles["summary"],
            prompt_version=DIGEST_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=character.id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
            pin_profile_id=runtime.pin_id,
            pin_profile_revision=runtime.pin_revision,
        )
        traced = TracedGateway(runtime.gateways["summary"], self._traces, spec)
        invocation = GraphInvocation(
            graph_name="memory-digest",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=run_id,
            actor_id=character.id,
            role="memory_digest",
            profile_version=traced.profile.version,
            prompt_version=DIGEST_PROMPT_VERSION,
            input={
                "owner_name": character.name,
                "day": day,
                "sources_text": sources_text,
                "source_ids": accepted_ids(tags),
            },
        )
        sampling = runtime.sampling
        graph = build_summary_graph(
            SummaryGraphDeps(
                gateway=traced,
                profile=runtime.profiles["summary"],
                system_template=load_digest_prompt(),
                temperature=sampling.temperature,
                top_p=sampling.top_p,
                top_k=sampling.top_k,
                max_tokens=role_max_tokens(sampling.max_tokens, "summary"),
            )
        )
        try:
            result = await invoke(graph, invocation)
        except Exception:
            await self._finish_task(task_run_id, owner, False)
            return False
        await self._finish_task(task_run_id, owner, True)
        proposal: dict[str, Any] = result.get("proposal") or {}
        text = str(proposal.get("text", "")) or f"Enduring traces: {len(source_ids)} older sources."
        raw_cited: list[Any] = untag([str(s) for s in proposal.get("source_ids", [])], tags)
        cited = [str(s) for s in raw_cited] or sorted(set(source_ids))
        async with self._factory() as uow:
            taken = await uow.digests.count_versions(world_id, character.id, day)
            await uow.digests.add(
                MemoryDigest(
                    id=new_digest_id(),
                    world_id=world_id,
                    owner_character_id=character.id,
                    text=text,
                    source_ids=cited,
                    day=day,
                    created_phase_index=index,
                    profile_version=traced.profile.version,
                    prompt_version=DIGEST_PROMPT_VERSION,
                    version=taken + 1,
                )
            )
            await uow.commit()
        return True

    async def _seal(self, world_id: UUID, run_id: UUID, index: int) -> SealedPhase:
        """Seal the shared snapshot every character decides from."""
        async with self._factory() as uow:
            characters = [c for c in await uow.characters.list_for_world(world_id)]
            world_version = await uow.versions.get(world_id) or 0
        members = sorted((c.id.hex, c.version) for c in characters)
        content_hash = _snapshot_hash(world_id, run_id, index, world_version, members)
        snapshot_id = derive_snapshot_id(run_id)
        snapshot = PhaseSnapshot(
            id=snapshot_id,
            world_id=world_id,
            phase_run_id=run_id,
            absolute_index=index,
            world_version=world_version,
            characters=[
                SnapshotCharacter(character_id=c.id, version=c.version) for c in characters
            ],
            content_hash=content_hash,
        )
        try:
            async with self._factory() as uow:
                await uow.phases.add_snapshot(snapshot)
                await uow.commit()
        except IntegrityError:
            pass
        sealed_versions = {f"character:{c.id}": c.version for c in characters}
        async with self._factory() as uow:
            away = await on_the_road(uow, world_id)
        await self._set_state(run_id, PhaseRunState.SNAPSHOT_SEALED)
        # Travellers are on the road, at no place: they neither decide, nor
        # react, nor see what happens where they set out from.
        return SealedPhase(
            snapshot_id=snapshot_id,
            versions=sealed_versions,
            locations={c.id: c.location_id for c in characters if c.id not in away},
        )

    async def _director_phase(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        sealed: SealedPhase,
        runtime: PhaseRuntime,
    ) -> str:
        """Run the Director when the cooldown elapsed; phases never block on it.

        The trigger is deterministic (world config); the model proposes at
        most one opportunity; validation enforces privileges and budgets.
        Every path sets DIRECTOR_COMPLETE. Outage leaves last-run
        untouched so the next phase retries; runs and rejections advance it.
        """
        async with self._factory() as uow:
            config = await uow.worlds.get_config(world_id)
            characters = await uow.characters.list_for_world(world_id)
            locations = await uow.locations.list_for_world(world_id)
            hooks = await uow.narrative.list_hooks_for_world(world_id)
            journeys = {
                a.character_id: UUID(str(a.payload["to_location_id"]))
                for a in await uow.activities.list_active_for_world(world_id)
                if a.kind == ActivityKind.TRAVEL and a.payload.get("to_location_id")
            }
            arcs = await uow.narrative.list_arcs_for_world(world_id)
            recent, quiet_streak, talk_streak, said = await _recent_happenings(uow, world_id)
            earlier = await _story_so_far(uow, world_id)
            intentions = {
                c.id: i.text
                for c in characters
                if (i := await uow.intentions.get(c.id)) is not None
            }
        last_raw = config.get("director.last_absolute")
        last = int(last_raw) if isinstance(last_raw, int) else None
        cooldown_raw = config.get("director.cooldown_phases")
        cooldown = int(cooldown_raw) if isinstance(cooldown_raw, int) else DIRECTOR_COOLDOWN_PHASES
        if not should_trigger(index, last, cooldown):
            await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
            return "skipped"
        task_run_id = derive_task_id(run_id, "director", world_id)
        owner = f"s1dir:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        known = [c.id for c in characters if c.life_status == LifeStatus.ALIVE]
        active_hooks = sum(1 for h in hooks if h.status != NarrativeStatus.CLOSED)
        active_arcs = sum(1 for a in arcs if a.status != NarrativeStatus.CLOSED)
        spawned_raw = config.get(SPAWNED_CONFIG_KEY)
        spawns_left = max(
            0, MAX_SPAWNED_NPCS - (spawned_raw if isinstance(spawned_raw, int) else 0)
        )
        added_raw = config.get(ADDED_PLACES_CONFIG_KEY)
        places_left = max(0, MAX_ADDED_PLACES - (added_raw if isinstance(added_raw, int) else 0))
        talk = [*said, *intentions.values(), *(h.purpose for h in hooks)]
        read: dict[str, list[str]] | None = None
        if self._local_models is not None:
            # Place spans the background reader cached; unread lines use the noun list.
            async with self._factory() as uow:
                read = await uow.mentions.places_for(MENTION_MODEL, talk)
        unmapped = unmapped_places(
            talk,
            # The region ("Ember Vale") is where everything is, not a missing place.
            [loc.name for loc in locations]
            + sorted({loc.region for loc in locations if loc.region}),
            read=read,
            people=[c.name for c in characters],
        )
        summary = (
            director_summary(
                index,
                characters,
                locations,
                hooks,
                arcs,
                recent,
                quiet_streak,
                intentions,
                talk_streak=talk_streak,
                earlier=earlier,
                journeys=journeys,
            )
            + f"\nNew characters you may still add to this story: {spawns_left}."
            + f"\nNew places you may still add to this story: {places_left}."
            + "\nPlaces mentioned but not on the map: "
            + (
                "; ".join(
                    f"{name} ({count} mention{'s' if count > 1 else ''})"
                    for name, count in unmapped
                )
                or "none"
            )
            + "."
            + _place_suggestion(unmapped, characters, locations, places_left)
        )
        suggested = _suggested_place(unmapped, characters, locations, places_left)
        hook_id = new_hook_id()
        arc_id = new_arc_id()
        spec = ManifestSpec(
            role="director",
            profile=runtime.profiles["director"],
            prompt_version=DIRECTOR_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            actor_id=world_id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
            pin_profile_id=runtime.pin_id,
            pin_profile_revision=runtime.pin_revision,
        )
        traced = TracedGateway(runtime.gateways["director"], self._traces, spec)
        invocation = GraphInvocation(
            graph_name="director-proposal",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
            role="director",
            profile_version=traced.profile.version,
            prompt_version=DIRECTOR_PROMPT_VERSION,
            input={
                "world_summary": summary,
                "trigger_ok": True,
                "trigger_reason": "cooldown elapsed",
                "known_character_ids": [str(c) for c in known],
                "active_hooks": active_hooks,
                "active_arcs": active_arcs,
                "hook_id": str(hook_id),
                "arc_id": str(arc_id),
                "world_id": str(world_id),
                "location_ids": [str(loc.id) for loc in locations],
                "spawns_left": spawns_left,
                # Deterministic per hook, so a replayed beat names the same person.
                "npc_id": str(uuid5(hook_id, "npc")),
                "item_id": str(uuid5(hook_id, "item")),
                "place_id": str(uuid5(hook_id, "place")),
                "places_left": places_left,
                "place_names": [loc.name for loc in locations],
                "open_hook_ids": [str(h.id) for h in hooks if h.status != NarrativeStatus.CLOSED],
                **(
                    {
                        "unmapped_place": suggested[0],
                        "unmapped_from": str(suggested[1].id),
                        "unmapped_from_name": suggested[1].name,
                    }
                    if suggested
                    else {}
                ),
            },
        )
        sampling = runtime.sampling
        graph = build_director_graph(
            DirectorGraphDeps(
                gateway=traced,
                profile=runtime.profiles["director"],
                system_template=load_director_prompt(),
                temperature=sampling.temperature,
                top_p=sampling.top_p,
                top_k=sampling.top_k,
                max_tokens=role_max_tokens(sampling.max_tokens, "director"),
            )
        )
        try:
            result = await invoke(graph, invocation)
        except Exception:
            await self._finish_task(task_run_id, owner, False)
            await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
            return "unavailable"
        if result.get("provider_failed"):
            # Outage: keep director.last_absolute so the next phase retries.
            await self._finish_task(task_run_id, owner, False)
            await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
            return "unavailable"
        await self._finish_task(task_run_id, owner, True)
        decision = DirectorDecision.model_validate(result.get("decision") or {})
        status = str(result.get("status", "noop"))
        async with self._factory() as uow:
            await accept_decision(
                uow,
                world_id,
                decision,
                "system",
                f"director:{run_id.hex}:{index}",
                index,
            )
        if decision.closed:
            # A settled rumour is experience for a combat story's party.
            await award_settled_hooks(
                self._factory,
                self._dnd_tables,
                world_id,
                [ending.hook_id for ending in decision.closed],
                absolute_index=index,
                run_id=run_id,
            )
        await self._set_state(run_id, PhaseRunState.DIRECTOR_COMPLETE)
        if decision.accepted:
            return "proposed"
        return status

    async def _decide_all(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        player_intents: Mapping[UUID, ActionIntent],
        directed: Mapping[UUID, tuple[ActionIntent, str]] | None = None,
        *,
        runtime: PhaseRuntime,
        submitter_id: UUID | None = None,
        grant_role: UserRole | None = None,
    ) -> list[Intent]:
        """Concurrent character decisions after the snapshot seal (barrier)."""
        async with self._factory() as uow:
            # Only characters sealed in this phase's snapshot decide: one the
            # director just added acts from the next beat.
            characters = [
                c
                for c in await uow.characters.list_for_world(world_id)
                if c.life_status == LifeStatus.ALIVE and c.id in sealed.locations
            ]
            locations = await uow.locations.list_for_world(world_id)
        known = [str(c.id) for c in characters]
        place_ids = [str(loc.id) for loc in locations]
        proposals = await asyncio.gather(
            *(
                self._bounded(
                    self._decide_one(
                        world_id,
                        run_id,
                        sealed,
                        character,
                        known,
                        place_ids,
                        player_intents,
                        directed or {},
                        runtime,
                        submitter_id,
                        grant_role,
                    )
                )
                for character in sorted(characters, key=lambda c: c.id.hex)
            )
        )
        return [intent for intent in proposals if intent is not None]

    async def _decide_one(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        character: Character,
        known: list[str],
        place_ids: list[str],
        player_intents: Mapping[UUID, ActionIntent],
        directed: Mapping[UUID, tuple[ActionIntent, str]],
        runtime: PhaseRuntime,
        submitter_id: UUID | None = None,
        grant_role: UserRole | None = None,
    ) -> Intent | None:
        if (
            player_intents.get(character.id) is None
            and (directed or {}).get(character.id) is None
            and character.id == runtime.controlled_character_id
        ):
            # Player agency: no model-authored decision for the controlled
            # character. Submitted intents and directed consequences apply below.
            return None
        task_run_id = derive_task_id(run_id, "character", character.id)
        owner = f"s1char:{run_id.hex[:8]}"
        await self._track_task(world_id, task_run_id, owner)
        player_action = player_intents.get(character.id)
        if player_action is not None and directed.get(character.id) is None:
            if grant_role == UserRole.PLAYER:
                allowed = character.id == runtime.controlled_character_id
            elif grant_role is None:
                allowed = character.id == submitter_id
            else:
                allowed = False
            if not allowed:
                raise DomainError(
                    ErrorCode.FORBIDDEN,
                    "player submission is stale for the admitted run",
                    {
                        "controlled_character_id": (
                            str(runtime.controlled_character_id)
                            if runtime.controlled_character_id is not None
                            else None
                        ),
                        "stale_actor_id": str(character.id),
                        "role": grant_role.value if grant_role is not None else None,
                    },
                )
        # Directed attempts first: advance_phase also merges them into
        # player_intents, and only a "direct:" key lets record_attempts
        # complete the queued step. Built as "player:", a directed attempt
        # was never completed and was replanned every phase.
        direct = directed.get(character.id)
        if direct is not None:
            direct_intent, ref = direct
            denial = precheck_action(
                direct_intent,
                known_character_ids=frozenset(known),
                location_ids=frozenset(place_ids),
            )
            if denial is not None:
                await self._finish_task(task_run_id, owner, False)
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED, f"directed intent rejected: {denial}"
                )
            intent = Intent(
                id=derive_intent_id(world_id, sealed.snapshot_id, character.id),
                world_id=world_id,
                snapshot_id=sealed.snapshot_id,
                phase_run_id=run_id,
                author_character_id=character.id,
                action=direct_intent,
                idempotency_key=f"direct:{ref}",
            )
            await self._finish_task(task_run_id, owner, True)
            return intent
        if player_action is not None:
            denial = precheck_action(
                player_action,
                known_character_ids=frozenset(known),
                location_ids=frozenset(place_ids),
            )
            if denial is not None:
                await self._finish_task(task_run_id, owner, False)
                raise DomainError(ErrorCode.VALIDATION_FAILED, f"player intent rejected: {denial}")
            intent = Intent(
                id=derive_intent_id(world_id, sealed.snapshot_id, character.id),
                world_id=world_id,
                snapshot_id=sealed.snapshot_id,
                phase_run_id=run_id,
                author_character_id=character.id,
                action=player_action,
                idempotency_key=f"player:{task_run_id}",
            )
            await self._finish_task(task_run_id, owner, True)
            return intent
        answered = await self._answered(world_id, character)

        async def _attempt(task_id: UUID, extra_goal: str | None) -> dict[str, Any]:
            task_run_id = task_id
            envelope, included, excluded = await self._context_for(
                world_id,
                run_id,
                sealed.snapshot_id,
                character,
                deciding=True,
                answered=answered,
                extra_goal=extra_goal,
            )
            sources, dropped = to_manifest_dict(included, excluded)
            # The same reads the context just made (shared within the phase).
            carried_ids = [
                str(i.id)
                for i in await self._shared(
                    ("carried", world_id, character.id),
                    lambda uow: uow.inventory.list_for_owner(world_id, character.id),
                )
            ]
            here_ids = [
                str(i.id)
                for i in await self._shared(
                    ("items_at", world_id, character.location_id),
                    lambda uow: uow.inventory.list_at_location(world_id, character.location_id),
                )
            ]
            spec = ManifestSpec(
                role="character_decision",
                profile=runtime.profiles["character"],
                prompt_version=CHARACTER_PROMPT_VERSION,
                world_id=world_id,
                phase_run_id=run_id,
                task_run_id=task_run_id,
                actor_id=character.id,
                sources=sources,
                budgets={},
                tokens={"total": envelope.total_estimated_tokens},
                dropped=dropped,
                pin_profile_id=runtime.pin_id,
                pin_profile_revision=runtime.pin_revision,
            )
            traced = TracedGateway(runtime.gateways["character"], self._traces, spec)
            invocation = GraphInvocation(
                graph_name="character-decision",
                graph_version="v1",
                task_run_id=task_run_id,
                world_id=world_id,
                phase_run_id=run_id,
                snapshot_id=sealed.snapshot_id,
                actor_id=character.id,
                context_manifest_id=envelope.manifest_id,
                role="character_decision",
                profile_version=traced.profile.version,
                prompt_version=CHARACTER_PROMPT_VERSION,
                input={
                    "rendered_context": envelope.rendered,
                    "actor_alive": True,
                    "known_character_ids": known,
                    "location_ids": place_ids,
                    "carried_item_ids": carried_ids,
                    "item_ids_here": here_ids,
                },
            )
            sampling = runtime.sampling
            graph = build_character_graph(
                CharacterGraphDeps(
                    gateway=traced,
                    profile=runtime.profiles["character"],
                    system_template=load_character_prompt(),
                    temperature=sampling.temperature,
                    top_p=sampling.top_p,
                    top_k=sampling.top_k,
                    max_tokens=sampling.max_tokens,
                )
            )
            return await invoke(graph, invocation)

        result = await _attempt(task_run_id, None)
        intent = Intent.model_validate(result["proposal"]["intent"])
        again = await self._repeats_answered(intent, answered)
        if again is not None:
            # Said and answered already: one more try with the answer in
            # view. The second answer stands, repeat or not.
            retry_id = derive_task_id(run_id, "character:again", character.id)
            await self._track_task(world_id, retry_id, owner)
            result = await _attempt(retry_id, again)
            intent = Intent.model_validate(result["proposal"]["intent"])
            await self._finish_task(retry_id, owner, True)
        await self._remember_intention(world_id, character.id, result.get("raw_response"))
        await self._finish_task(task_run_id, owner, True)
        return intent

    async def _answered(self, world_id: UUID, character: Character) -> list[Exchange]:
        """This character's recently answered exchanges, newest first."""
        async with self._factory() as uow:
            _day, _phase, now_index = await uow.worlds.get_clock(world_id)
            observations = await uow.perception.observations_for_observer(
                character.id,
                100000,
                since_phase_index=max(0, now_index - ANSWERED_WINDOW_PHASES),
                min_salience=MAX_SALIENCE + 1,
            )
        lines = sorted(
            (
                (obs.created_phase_index, 1 if fact.key.startswith("reply:") else 0, fact.value)
                for obs in observations
                for fact in obs.facts
                if fact.key in ("attempt:communicate", "reply:communicate")
            ),
            key=lambda line: (line[0], line[1]),
        )
        return answered_exchanges([(phase, value) for phase, _o, value in lines], character.name)

    async def _repeats_answered(
        self, proposed: Intent | Reaction, answered: Sequence[Exchange]
    ) -> str | None:
        """A retry note when a spoken decision or reply repeats an answered exchange."""
        action = proposed.action
        if not isinstance(action, CommunicateAction) or not answered:
            return None
        line = action.topic.strip().strip('"')
        similarity: dict[int, float] | None = None
        if self._local_models is not None:
            try:
                found = await self._local_models.embed(
                    [line, *(e.said for e in answered)], "document"
                )
                first, *rest = found.vectors
                similarity = {
                    i: sum(a * b for a, b in zip(first, vec, strict=True))
                    for i, vec in enumerate(rest)
                }
            except LocalModelsUnavailable:
                similarity = None
        exchange = repeated(line, answered, similarity)
        return None if exchange is None else retry_note(line, exchange)

    async def _track_task(self, world_id: UUID, task_id: UUID, owner: str) -> None:
        """Audit-only task row for a character decision (recovery stays with commits)."""
        async with self._factory() as uow:
            key = f"s1char:{task_id.hex}"
            existing = await uow.tasks.find_by_key(world_id, key)
            if existing is None:
                try:
                    await uow.tasks.create(task_id, world_id, "character_decision", key)
                    await uow.commit()
                except IntegrityError:
                    await uow.rollback()
            await uow.tasks.claim(
                task_id,
                owner,
                Lease(
                    owner=owner,
                    claimed_at=utcnow(),
                    expires_at=utcnow() + timedelta(seconds=60),
                    attempt=1,
                    max_attempts=3,
                    input_version=1,
                    idempotency_key=f"s1char:{task_id.hex}",
                ),
            )
            await uow.commit()

    async def _finish_task(self, task_id: UUID, owner: str, ok: bool) -> None:
        async with self._factory() as uow:
            await uow.tasks.finish(task_id, owner, "succeeded" if ok else "dead_letter")
            await uow.commit()

    async def _remember_intention(self, world_id: UUID, character_id: UUID, raw: object) -> None:
        """Keep the character's newly stated intention (the newest replaces the old)."""
        text = extract_intention(raw if isinstance(raw, str) else None)
        if text is None:
            return
        async with self._factory() as uow:
            _day, _phase, now_index = await uow.worlds.get_clock(world_id)
            await uow.intentions.set(
                CharacterIntention(
                    character_id=character_id,
                    world_id=world_id,
                    text=text,
                    set_phase_index=now_index,
                )
            )
            await uow.commit()

    async def _context_for(
        self,
        world_id: UUID,
        run_id: UUID,
        snapshot_id: UUID,
        character: Character,
        *,
        deciding: bool = False,
        answered: Sequence[Exchange] = (),
        extra_goal: str | None = None,
    ) -> tuple[ContextEnvelope, list[ManifestSource], list[ManifestSource]]:
        """Perspective candidates for one character (filters before ranking).

        ``deciding`` (a turn, not a reply) adds a note when the character's
        own last turns were all talk or all idling.
        """
        world = await self._world_view(world_id)
        config, now_index = world.config, world.now_index
        items_here = await self._shared(
            ("items_at", world_id, character.location_id),
            lambda uow: uow.inventory.list_at_location(world_id, character.location_id),
        )
        carried = await self._shared(
            ("carried", world_id, character.id),
            lambda uow: uow.inventory.list_for_owner(world_id, character.id),
        )
        half_life = _config_int(config, HALF_LIFE_PHASES_KEY, DEFAULT_HALF_LIFE_PHASES)
        recent_phases = _config_int(config, RECENT_PHASES_KEY, DEFAULT_RECENT_PHASES)
        floor = _config_float(config, SALIENCE_FLOOR_KEY, DEFAULT_SALIENCE_FLOOR)
        since = max(0, now_index - recent_phases)

        async def load_mind(uow: Any) -> _Mind:
            return _Mind(
                observations=await uow.perception.observations_for_observer(
                    character.id,
                    100000,
                    since_phase_index=since,
                    min_salience=floor,
                    older_limit=OLDER_SALIENT_KEPT,
                ),
                memories=await uow.perception.memories_for_owner(
                    character.id,
                    since_phase_index=since,
                    min_salience=floor,
                    older_limit=OLDER_SALIENT_KEPT,
                ),
                relationships=await uow.relationships.list_for_character(world_id, character.id),
                digests=await uow.digests.list_for_owner(world_id, character.id),
                families=(
                    await uow.scenes.recent_families(character.id, STREAK_TURNS) if deciding else []
                ),
            )

        # A reactor answering several attempts read all of this once per
        # attempt; nothing in a phase writes it (perf-reads-001). The
        # intention is read fresh: a reply may restate it mid-phase.
        mind = await self._shared(("mind", world_id, character.id, since, deciding), load_mind)
        observations, memories = mind.observations, mind.memories
        relationships, digests, families = mind.relationships, mind.digests, mind.families
        async with self._factory() as uow:
            card = await _card_of(uow, character, self._cards)
            place = world.place(character.location_id) or await uow.locations.get(
                character.location_id
            )
            intention = await uow.intentions.get(character.id)
            hooks = world.hooks
            everyone = world.everyone
            present = [c for c in everyone if c.id not in world.away]
            place_names = {loc.id: loc.name for loc in world.locations}
            pronouns = await _pronouns_of(
                uow,
                [c for c in present if c.location_id == place.id and c.id != character.id],
                self._cards,
            )
        names = {c.id: c.name for c in everyone}
        candidates = [
            SourceCandidate(
                source_id=f"card:{character.id}",
                data_class="identity",
                visibility=Visibility.PRIVATE,
                owner_id=character.id,
                text=identity_text(card),
                score=3.0,
            ),
            SourceCandidate(
                source_id=f"place:{place.id}",
                data_class="surroundings",
                visibility=Visibility.PUBLIC,
                text=surroundings_text(
                    place, place_names, present, character.id, items_here, pronouns
                ),
                score=2.0,
            ),
            SourceCandidate(
                source_id=f"state:{character.id}",
                data_class="own_state",
                visibility=Visibility.PRIVATE,
                owner_id=character.id,
                text=(
                    f"now {phase_label(now_index)}, "
                    f"character_id {character.id}, snapshot_id {snapshot_id}, "
                    f"stamina {character.stamina}, mana {character.mana}, "
                    f"carrying {'; '.join(item_line(i) for i in carried) or 'nothing'}, "
                    f"status {character.life_status.value}, "
                    f"conditions {','.join(character.conditions) or 'none'}"
                ),
                score=2.0,
            ),
        ]
        for number, drive in enumerate(card_drives(card.personality)):
            candidates.append(
                SourceCandidate(
                    source_id=f"drive:{character.id}:{number}",
                    data_class="goals",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=drive,
                    score=2.0,
                )
            )
        for hook in hooks:
            if hook.participant_ids and character.id not in hook.participant_ids:
                continue
            if hook.status == NarrativeStatus.CLOSED:
                # How a recent rumour ended, so nobody keeps chasing a job
                # that is done (closed hooks used to vanish without a trace).
                closed = hook.closed_phase_index
                if (
                    hook.ending
                    and closed is not None
                    and now_index - closed <= SETTLED_MEMORY_PHASES
                ):
                    candidates.append(
                        SourceCandidate(
                            source_id=f"settled:{hook.id}",
                            data_class="lore",
                            visibility=Visibility.PUBLIC,
                            text=f"Settled around the vale: {hook.title}. {hook.ending}".strip(),
                            score=1.5,
                            created_phase_index=closed,
                        )
                    )
                continue
            candidates.append(
                SourceCandidate(
                    source_id=f"hook:{hook.id}",
                    data_class="lore",
                    visibility=Visibility.PUBLIC,
                    text=f"Word around the vale: {hook.title}. {hook.purpose}".strip(),
                    score=2.0,
                    created_phase_index=hook.created_phase_index,
                )
            )
        if answered:
            candidates.append(
                SourceCandidate(
                    source_id=f"answered:{character.id}",
                    data_class="goals",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=settled_note(answered[:ANSWERED_SHOWN]),
                    score=2.5,
                )
            )
        if extra_goal is not None:
            candidates.append(
                SourceCandidate(
                    source_id=f"again:{character.id}",
                    data_class="goals",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=extra_goal,
                    score=4.0,
                )
            )
        note = streak_note(families, intention.text if intention is not None else None)
        if note is not None:
            candidates.append(
                SourceCandidate(
                    source_id=f"streak:{character.id}",
                    data_class="goals",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=note,
                    score=3.5,
                )
            )
        if intention is not None:
            candidates.append(
                SourceCandidate(
                    source_id=f"intention:{character.id}",
                    data_class="goals",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=(
                        f"Your current intention (since "
                        f"{phase_label(intention.set_phase_index)}): {intention.text}"
                    ),
                    score=3.0,
                    created_phase_index=intention.set_phase_index,
                )
            )
        for obs in observations:
            for fact in obs.facts:
                candidates.append(
                    SourceCandidate(
                        source_id=f"obs:{obs.id}:{fact.key}",
                        data_class="observations",
                        visibility=Visibility.PRIVATE,
                        owner_id=character.id,
                        text=_observation_line(obs.created_phase_index, fact.key, fact.value),
                        score=score_salience(
                            obs.salience, now_index - obs.created_phase_index, half_life
                        ),
                        created_phase_index=obs.created_phase_index,
                        ordinal=1 if fact.key.startswith("reply:") else 0,
                    )
                )
        for relationship in relationships:
            outgoing = relationship.source_id == character.id
            other = relationship.target_id if outgoing else relationship.source_id
            candidates.append(
                SourceCandidate(
                    source_id=f"rel:{relationship.id}",
                    data_class="relationships",
                    visibility=Visibility.PRIVATE,
                    owner_id=relationship.source_id,
                    text=describe(relationship, names.get(other, other.hex[:8])),
                    score=1.5,
                )
            )
        for memory in memories:
            candidates.append(
                SourceCandidate(
                    source_id=f"mem:{memory.id}",
                    data_class="memories",
                    visibility=memory.visibility,
                    owner_id=character.id,
                    text=f"{phase_label(memory.created_phase_index)}: {memory.text}",
                    score=score_salience(
                        memory.salience, now_index - memory.created_phase_index, half_life
                    ),
                    created_phase_index=memory.created_phase_index,
                )
            )
        for digest in digests:
            candidates.append(
                SourceCandidate(
                    source_id=f"digest:{digest.id}",
                    data_class="memories",
                    visibility=Visibility.PRIVATE,
                    owner_id=character.id,
                    text=digest.text,
                    score=DIGEST_SCORE,
                    created_phase_index=digest.created_phase_index,
                )
            )
        if self._local_models is not None:
            focus = _recall_focus(
                character,
                place.name,
                [c.name for c in everyone if c.location_id == place.id and c.id != character.id],
                intention.text if intention is not None else None,
                [item_label(i) for i in carried],
                [c.text for c in candidates if c.data_class == "observations"][-3:],
            )
            candidates = await self._recall_by_relevance(
                character.id,
                candidates,
                focus,
                since=since,
                now_index=now_index,
                half_life=half_life,
                weight=_config_float(config, RELEVANCE_WEIGHT_KEY, DEFAULT_RELEVANCE_WEIGHT),
            )
        request = ContextRequest(
            role="character_decision",
            actor_id=character.id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=snapshot_id,
            purpose="decide next intent",
            section_budgets=DECISION_SECTION_BUDGETS,
        )
        envelope, included, excluded = assemble(request, candidates)
        if phase_reads.VERIFY and phase_reads.active() is not None:
            with phase_reads.sharing(None):
                fresh, *_rest = await self._context_for(
                    world_id,
                    run_id,
                    snapshot_id,
                    character,
                    deciding=deciding,
                    answered=answered,
                    extra_goal=extra_goal,
                )
            if fresh.rendered != envelope.rendered:
                diff = difflib.unified_diff(
                    fresh.rendered.splitlines(),
                    envelope.rendered.splitlines(),
                    "fresh",
                    "shared",
                    lineterm="",
                )
                raise AssertionError(
                    f"shared reads changed {character.name}'s context: " + " | ".join(diff)
                )
        return envelope, included, excluded

    async def _shared[T](self, key: object, load: Callable[[Any], Awaitable[T]]) -> T:
        """One read per phase while a phase view is shared, else a fresh one."""

        async def fresh() -> T:
            async with self._factory() as uow:
                return await load(uow)

        reads = phase_reads.active()
        return await (reads.get(key, fresh) if reads is not None else fresh())

    async def _world_view(self, world_id: UUID) -> _WorldView:
        """Config, clock, rumours, people, travellers and places (see phase_reads)."""

        async def load(uow: Any) -> _WorldView:
            config = await uow.worlds.get_config(world_id)
            _day, _phase, now_index = await uow.worlds.get_clock(world_id)
            return _WorldView(
                config=config,
                now_index=now_index,
                hooks=await uow.narrative.list_hooks_for_world(world_id),
                everyone=await uow.characters.list_for_world(world_id),
                away=await on_the_road(uow, world_id),
                locations=await uow.locations.list_for_world(world_id),
            )

        return await self._shared(("world", world_id), load)

    async def _recall_by_relevance(
        self,
        owner_id: UUID,
        candidates: list[SourceCandidate],
        focus: str,
        *,
        since: int,
        now_index: int,
        half_life: int,
        weight: float,
    ) -> list[SourceCandidate]:
        """Lift what bears on the moment; bring back close older rows.

        Recency and salience still set the base score; similarity to the
        focus adds up to ``weight`` on top. Anything not yet indexed, or
        a local service that is off, leaves the scores as they were.
        """
        assert self._local_models is not None
        try:
            found = await self._local_models.embed([focus], "query")
        except LocalModelsUnavailable:
            return candidates
        query, model = found.vectors[0], found.model
        recallable = [c.source_id for c in candidates if c.source_id.startswith(("obs:", "mem:"))]
        async with self._factory() as uow:
            similar = await uow.recall.similarities(owner_id, model, query, recallable)
            older = await uow.recall.nearest_before(
                owner_id,
                model,
                query,
                since,
                recallable,
                RECALL_OLD_MIN_SIMILARITY,
                RECALL_OLD_LIMIT,
            )
        lifted = [
            c.model_copy(update={"score": c.score + weight * relevance(similar[c.source_id])})
            if c.source_id in similar
            else c
            for c in candidates
        ]
        for source, similarity in older:
            lifted.append(
                SourceCandidate(
                    source_id=source.source_id,
                    data_class="memories"
                    if source.source_id.startswith("mem:")
                    else "observations",
                    visibility=Visibility.PRIVATE,
                    owner_id=owner_id,
                    text=f"{phase_label(source.created_phase_index)}: {source.text}",
                    score=score_salience(1.0, now_index - source.created_phase_index, half_life)
                    + weight * relevance(similarity),
                    created_phase_index=source.created_phase_index,
                )
            )
        return lifted

    async def _commit_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        sealed: SealedPhase,
        scene: Scene,
        intents: list[Intent],
        names: Mapping[UUID, str],
        quiet: bool = False,
        over_budget: bool = False,
        *,
        runtime: PhaseRuntime,
        timings: dict[str, int] | None = None,
        narrate: bool = True,
    ) -> SceneOutcome:
        """React, resolve, commit, and narrate one scene (sequential barrier).

        With ``narrate=False`` the scene is committed and settled only; the
        caller narrates it later (see _narrate_outcome), alongside others.
        """
        # One world read for this scene's reactions, taken now (a redone
        # scene reads the world as the earlier commits left it).
        with phase_reads.sharing(phase_reads.PhaseReads()):
            prepared = await self._prepare_scene(
                world_id, run_id, sealed, scene, intents, names, runtime=runtime, timings=timings
            )
        outcome = await self._commit_prepared(world_id, run_id, index, sealed, scene, prepared)
        if not narrate:
            return outcome
        self._fire("before_narration")
        with _timed(timings if timings is not None else {}, "narrate"):
            return await self._narrate_outcome(
                world_id, run_id, scene, outcome, quiet, over_budget, runtime
            )

    async def _prepare_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        intents: list[Intent],
        names: Mapping[UUID, str],
        *,
        runtime: PhaseRuntime,
        timings: dict[str, int] | None = None,
    ) -> PreparedScene:
        """The model work for one scene: reactions, then the resolution.

        Reads only, so the scenes of a beat (different people, different
        places) prepare side by side; their commits stay in order.
        """
        stage_ms: dict[str, int] = timings if timings is not None else {}
        members = [i for i in intents if i.id in scene.intent_ids]
        attempts = [
            Attempt(
                id=derive_attempt_id(i.id),
                world_id=world_id,
                intent_id=i.id,
                scene_id=scene.id,
                actor_character_id=i.author_character_id,
                observable_summary=_summarize(i.action, names, i.author_character_id),
            )
            for i in sorted(members, key=lambda x: str(x.id))
        ]
        aimed_at = {
            derive_attempt_id(i.id): getattr(i.action, "target_character_id", None) for i in members
        }
        with _timed(stage_ms, "react"):
            reactions = await self._react_all(
                world_id, run_id, sealed, scene, attempts, names, runtime, aimed_at
            )
        with _timed(stage_ms, "resolve"):
            resolution, live_versions = await self._resolve_scene(
                world_id, run_id, sealed, scene, members, runtime
            )
        observations, memories = self._perceive_scene(
            world_id, sealed, scene, members, names, reactions, resolution.outcome.value
        )
        return PreparedScene(
            members, attempts, reactions, resolution, live_versions, observations, memories
        )

    async def _commit_prepared(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        sealed: SealedPhase,
        scene: Scene,
        prepared: PreparedScene,
    ) -> SceneOutcome:
        """Commit one prepared scene and settle its verbs."""
        members, attempts, reactions = prepared.members, prepared.attempts, prepared.reactions
        resolution, live_versions = prepared.resolution, prepared.live_versions
        observations, memories = prepared.observations, prepared.memories
        # Only the aggregates this scene mutates enter the version check,
        # pinned to the versions the resolver just validated.
        touched = {
            key.split(":", 1)[-1]: live_versions[key]
            for key in scene.mutable_aggregate_ids
            if key in live_versions
        }
        # A road longer than one phase is a journey: the traveller pays its
        # stamina now and sets off, arriving when its phases have passed.
        async with self._factory() as uow:
            roads = {
                route.id: route
                for place in await uow.locations.list_for_world(world_id)
                for route in place.routes
            }
        effects, journeys = split_journeys(list(resolution.effects), roads)
        result = await self._canonical.commit(
            build_scene_commit(
                command_id=uuid4(),
                scene=scene,
                intents=members,
                attempts=attempts,
                reactions=reactions,
                resolution=resolution,
                effects=effects,
                expected_versions=touched,
                absolute_index=index,
                observations=observations,
                memories=memories,
                location_id=scene_location(scene, sealed.locations, effects),
            )
        )
        # A directed attempt is completed only now that its execution is
        # durably recorded: the scene event is the proof.
        directed_outcomes = [
            (member.idempotency_key[len("direct:") :], result.event_id)
            for member in members
            if member.idempotency_key.startswith("direct:")
        ]
        if directed_outcomes:
            await record_attempts(self._factory, directed_outcomes)
        if journeys:
            await self._set_off(world_id, index, scene.id, journeys)
        settled = [e.hook_id for e in effects if isinstance(e, HookSettledEffect)]
        if settled:
            await award_settled_hooks(
                self._factory,
                self._dnd_tables,
                world_id,
                settled,
                absolute_index=index,
                run_id=run_id,
                scene_event_id=result.event_id,
            )
        if resolution.outcome == ResolutionOutcome.SUCCESS:
            await self._settle_scene_verbs(world_id, run_id, index, scene, members, result.event_id)
        try:
            await self._join_invited(world_id, attempts, reactions)
        except DomainError:
            # A join that fails (a full party, a race) never fails the turn.
            _phase_log.warning("joining the party failed", exc_info=True)
        return SceneOutcome(
            scene_id=scene.id,
            event_id=result.event_id,
            resolution_outcome=resolution.outcome.value,
            narration="pending",
        )

    async def _set_off(
        self,
        world_id: UUID,
        index: int,
        scene_id: UUID,
        journeys: Sequence[tuple[MoveEntityEffect, Route]],
    ) -> None:
        """Start each journey a committed scene set out on (once per scene and
        traveller); whatever a traveller was doing here ends as they leave."""
        async with self._factory() as uow:
            active = {
                a.character_id: a for a in await uow.activities.list_active_for_world(world_id)
            }
            for move, route in journeys:
                for character_id in move.affected_ids:
                    key = f"journey:{scene_id.hex}:{character_id.hex}"
                    if await uow.activities.get_by_direct_step_key(world_id, key) is not None:
                        continue
                    doing = active.get(character_id)
                    if doing is not None:
                        await uow.activities.save(
                            doing.model_copy(
                                update={
                                    "status": ActivityStatus.CANCELLED,
                                    "progress_phases": effective_progress(doing, index),
                                }
                            ),
                            doing.version,
                        )
                    await uow.activities.add(
                        Activity(
                            id=new_activity_id(),
                            world_id=world_id,
                            character_id=character_id,
                            kind=ActivityKind.TRAVEL,
                            status=ActivityStatus.ACTIVE,
                            start_absolute=index,
                            duration_phases=route.duration_phases,
                            payload={
                                "from_location_id": str(move.from_location_id),
                                "to_location_id": str(move.to_location_id),
                                "route_id": str(route.id),
                                # Paid on setting off, with the scene.
                                "stamina_cost": 0,
                            },
                            direct_step_key=key,
                        )
                    )
            await uow.commit()

    async def _narrate_outcome(
        self,
        world_id: UUID,
        run_id: UUID,
        scene: Scene,
        outcome: SceneOutcome,
        quiet: bool,
        over_budget: bool,
        runtime: PhaseRuntime,
    ) -> SceneOutcome:
        """Narrate one committed scene and report how its words were made."""
        narration = await self._narrate_scene(
            world_id, run_id, scene, outcome.event_id, quiet, over_budget, runtime=runtime
        )
        # The narration source is persisted atomically with its beats
        # inside _narrate_scene; "skipped" writes nothing. When beats
        # pre-existed, report the recorded source when known instead of
        # the skip itself.
        if narration == "skipped":
            async with self._factory() as uow:
                stored = await uow.scenes.get_scene(scene.id)
                if stored.narration_status is not None:
                    narration = stored.narration_status
        return replace(outcome, narration=narration)

    async def _settle_scene_verbs(
        self,
        world_id: UUID,
        run_id: UUID,
        index: int,
        scene: Scene,
        members: list[Intent],
        event_id: UUID,
    ) -> None:
        """Settle v2 verb intents after the scene commit, idempotently.

        Each verb writes a settle-gate command row first: a replayed
        phase collides on the gate and skips work it already did, so a
        crash between scenes can never double-apply a bout, claim, or
        handoff. Gate plus work share one transaction; anything else
        rolls back and the phase fails loud for a safe retry.
        """
        for intent in members:
            action = intent.action
            if not isinstance(action, (SparAction, AppealAction, TransferAction, TakeAction)):
                continue
            async with self._factory() as uow:
                try:
                    await uow.commands.add(
                        command_id=uuid4(),
                        world_id=world_id,
                        key=f"settle:{intent.id.hex}",
                        actor_role="system",
                        command_type="settle_verb",
                        expected_versions={},
                        payload={
                            "intent_id": str(intent.id),
                            "scene_id": str(scene.id),
                            "family": action.family.value,
                        },
                        input_hash=canonical_input_hash({"intent_id": str(intent.id)}),
                    )
                except DomainError as exc:
                    if exc.code is ErrorCode.IDEMPOTENCY_CONFLICT:
                        continue
                    raise
                if isinstance(action, SparAction):
                    await self._settle_spar(uow, world_id, run_id, index, intent, action, event_id)
                elif isinstance(action, AppealAction):
                    text = normalize(action.proposition)
                    if not text:
                        raise DomainError(ErrorCode.VALIDATION_FAILED, "appeals need a proposition")
                    await fold_claim(
                        uow,
                        world_id,
                        intent.author_character_id,
                        text,
                        action.audience_location_id,
                        index,
                        None,
                        event_id,
                    )
                elif isinstance(action, TakeAction):
                    await self._settle_take(uow, intent, action)
                else:
                    assert isinstance(action, TransferAction)
                    await self._settle_transfer(uow, intent, action)
                await uow.commit()

    async def _settle_spar(
        self,
        uow: Any,
        world_id: UUID,
        run_id: UUID,
        index: int,
        intent: Intent,
        action: SparAction,
        event_id: UUID,
    ) -> None:
        """One seeded attack exchange between roster sheets, persisted once."""
        roster = await uow.party.list_for_world(world_id)
        author = await uow.characters.get(intent.author_character_id)
        target = await uow.characters.get(action.target_character_id)
        by_name = {member.name_key: member for member in roster}
        attacker = by_name.get(party_name_key(author.name))
        defender = by_name.get(party_name_key(target.name))
        # A bout needs two sheets with health and a weapon. Without them it is
        # just talk of sparring: no roll. It used to raise here, after the
        # scene had committed, and the half-done turn blocked every later one
        # (an NPC without a sheet chose to spar with the hero, combat-depth-002).
        if attacker is None or defender is None:
            return
        # Sheets as they woke today: a new story day was the night's rest.
        day = split_absolute(index)[0]
        striker, struck = long_rest(attacker.sheet, day), long_rest(defender.sheet, day)
        if striker.hp is None or struck.hp is None or not striker.weapons:
            return
        weapon_key = action.weapon if action.weapon in striker.weapons else striker.weapons[0]
        tables = self._dnd_tables()
        weapons = table(tables, "weapons")
        weapon = entry(weapons, weapon_key)
        bonus = weapon_attack_bonus(tables, striker, weapon)
        target_ac = armor_ac(tables, struck)
        digest = hashlib.sha256(str(event_id).encode()).digest()[:8]
        seed = int.from_bytes(digest, "big") & ((1 << 63) - 1)
        rng = random.Random(seed).random
        attack = roll_attack(bonus, target_ac, rng)
        damage = dict_field(weapon, "damage")
        dtype = str_field(damage, "type") or "damage"
        if attack.hit:
            rolled = weapon_damage(
                tables, striker, weapon, roll_damage(str_field(damage, "dice"), rng, attack.crit)
            )
            after = max(0, struck.hp.current - rolled)
            before_hp = struck.hp.current
            outcome = (
                f"{attacker.name} hits {defender.name} for {rolled} {dtype} "
                f"({before_hp}->{after} HP)"
            )
        else:
            rolled = 0
            after = struck.hp.current
            outcome = f"{attacker.name} misses {defender.name} ({attack.total} vs AC {target_ac})"
        defender_sheet = struck.model_copy(deep=True)
        assert defender_sheet.hp is not None
        defender_sheet.hp.current = after
        await uow.party.save_sheet(defender.id, defender_sheet, defender.version)
        combat_id = derive_combat_event_id(event_id)
        sequence = await uow.events.max_sequence(world_id) + 1
        await uow.events.append_event(
            WorldEvent(
                id=combat_id,
                world_id=world_id,
                sequence=sequence,
                event_type=EventType.ACTION_RESOLVED,
                absolute_index=index,
                phase_run_id=run_id,
                participant_ids=sorted(
                    [intent.author_character_id, action.target_character_id], key=str
                ),
                summary={
                    "spar": outcome[:512],
                    "scene_event_id": str(event_id),
                    "rolls": combat_rolls_json(
                        [
                            TagOutcome(
                                kind="spar",
                                text=f"{outcome}.",
                                actor=attacker.name,
                                target=defender.name,
                                using=str(weapon.get("name", weapon_key)),
                                roll=attack.total,
                                natural=attack.nat,
                                ac=target_ac,
                                result=("crit" if attack.crit else "hit") if attack.hit else "miss",
                                amount=rolled if attack.hit else None,
                                damage_type=dtype if attack.hit else None,
                                hp_before=struck.hp.current if attack.hit else None,
                                hp_after=after if attack.hit else None,
                            )
                        ],
                        [],
                    ),
                },
                random_seed=seed,
                random_algorithm="seeded-d20-v1",
                random_result=outcome[:512],
            )
        )

    async def _settle_take(self, uow: Any, intent: Intent, action: TakeAction) -> None:
        """Pick up an unheld item where the taker stands; gone already is a no-op."""
        try:
            item = await uow.inventory.get_item(action.item_instance_id)
        except DomainError:
            return
        taker = await uow.characters.get(intent.author_character_id)
        if item.owner_id is not None or item.location_id != taker.location_id:
            return  # someone was quicker, or it was never here
        await move_item(uow, item, taker.id)

    async def _settle_transfer(self, uow: Any, intent: Intent, action: TransferAction) -> None:
        """Ownership-checked handoff between co-located characters."""
        item = await uow.inventory.get_item(action.item_instance_id)
        if item.owner_id != intent.author_character_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "handover needs ownership")
        author = await uow.characters.get(intent.author_character_id)
        target = await uow.characters.get(action.target_character_id)
        if target.world_id != item.world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "recipient is not in this world")
        if target.location_id != author.location_id:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "handoff needs shared ground")
        await move_item(uow, item, action.target_character_id)

    async def _react_all(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        attempts: list[Attempt],
        names: Mapping[UUID, str],
        runtime: PhaseRuntime,
        aimed_at: Mapping[UUID, UUID | None] | None = None,
    ) -> list[Reaction]:
        """One bounded reaction graph per eligible (attempt, reactor) pair.

        Every pair runs at once: each has its own task and graph thread and
        reads only the sealed snapshot and its own attempt (a reactor with
        two attempts to answer used to answer them one after the other).
        Results keep the attempt-major, participant-minor order of the
        former sequential loop.
        """
        participant_ids = [str(p.character_id) for p in scene.participants]
        pairs: dict[UUID, list[tuple[int, Attempt]]] = {}
        for index, attempt in enumerate(attempts):
            eligible = [
                p.character_id
                for p in scene.participants
                if p.character_id != attempt.actor_character_id
                # Player agency: the controlled character reacts only
                # through submitted player intents, never model prose.
                and p.character_id != runtime.controlled_character_id
            ]
            target = (aimed_at or {}).get(attempt.id)
            for reactor_id in choose_reactors(
                attempt.id, eligible, target, self._reacting_bystanders
            ):
                pairs.setdefault(reactor_id, []).append((index, attempt))
        order = {p.character_id: rank for rank, p in enumerate(scene.participants)}

        async def _pair(
            reactor_id: UUID, index: int, attempt: Attempt
        ) -> tuple[int, int, Reaction] | None:
            reaction = await self._bounded(
                self._react_one(
                    world_id,
                    run_id,
                    sealed,
                    scene,
                    attempt,
                    reactor_id,
                    participant_ids,
                    names,
                    runtime,
                )
            )
            return None if reaction is None else (index, order[reactor_id], reaction)

        gathered = await asyncio.gather(
            *(_pair(r, index, attempt) for r, todo in pairs.items() for index, attempt in todo)
        )
        ranked = sorted((item for item in gathered if item is not None), key=lambda t: (t[0], t[1]))
        return [reaction for _, _, reaction in ranked]

    async def _react_one(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        attempt: Attempt,
        reactor_id: UUID,
        participant_ids: list[str],
        names: Mapping[UUID, str],
        runtime: PhaseRuntime,
    ) -> Reaction | None:
        world = await self._world_view(world_id)
        reactor = world.person(reactor_id)
        if reactor is None:
            async with self._factory() as uow:
                reactor = await uow.characters.get(reactor_id)
        locations = world.locations
        if phase_reads.VERIFY and phase_reads.active() is not None:
            async with self._factory() as uow:
                fresh_reactor = await uow.characters.get(reactor_id)
                fresh_places = await uow.locations.list_for_world(world_id)
            if (fresh_reactor, fresh_places) != (reactor, locations):
                raise AssertionError(f"shared reads changed {reactor.name}'s reaction input")
        # What this reactor already asked and heard answered: shown in the
        # context, and a reply that asks it again gets one more try, as
        # decisions do (729a04a). Read once per phase per reactor.
        reads = phase_reads.active()
        answered = await (
            reads.get(("answered", world_id, reactor_id), lambda: self._answered(world_id, reactor))
            if reads is not None
            else self._answered(world_id, reactor)
        )

        async def _attempt(task_run_id: UUID, extra_goal: str | None) -> dict[str, Any]:
            envelope, included, excluded = await self._context_for(
                world_id,
                run_id,
                sealed.snapshot_id,
                reactor,
                answered=answered,
                extra_goal=extra_goal,
            )
            sources, dropped = to_manifest_dict(included, excluded)
            spec = ManifestSpec(
                role="reaction",
                profile=runtime.profiles["reaction"],
                prompt_version=REACTION_PROMPT_VERSION,
                world_id=world_id,
                phase_run_id=run_id,
                task_run_id=task_run_id,
                actor_id=reactor_id,
                sources=sources,
                budgets={},
                tokens={"total": envelope.total_estimated_tokens},
                dropped=dropped,
                pin_profile_id=runtime.pin_id,
                pin_profile_revision=runtime.pin_revision,
            )
            traced = TracedGateway(runtime.gateways["reaction"], self._traces, spec)
            invocation = GraphInvocation(
                graph_name="reaction",
                graph_version="v1",
                task_run_id=task_run_id,
                world_id=world_id,
                phase_run_id=run_id,
                snapshot_id=sealed.snapshot_id,
                scene_id=scene.id,
                actor_id=reactor_id,
                context_manifest_id=envelope.manifest_id,
                role="reaction",
                profile_version=traced.profile.version,
                prompt_version=REACTION_PROMPT_VERSION,
                input={
                    "reactor_context": envelope.rendered,
                    "observable_summary": attempt.observable_summary,
                    "reactor_alive": True,
                    "reactor_location_id": str(reactor.location_id),
                    "event_location_id": str(sealed.locations.get(attempt.actor_character_id)),
                    "participant_ids": participant_ids,
                    "known_character_ids": [str(c) for c in sealed.locations],
                    "known_characters": [
                        {"id": str(c), "name": names.get(c, c.hex[:8])} for c in sealed.locations
                    ],
                    "location_ids": [str(loc.id) for loc in locations],
                    "beats_remaining": scene.beat_budget,
                    "attempt_id": str(attempt.id),
                    "attempt_actor_id": str(attempt.actor_character_id),
                },
            )
            sampling = runtime.sampling
            graph = build_reaction_graph(
                ReactionGraphDeps(
                    gateway=traced,
                    profile=runtime.profiles["reaction"],
                    system_template=load_reaction_prompt(),
                    temperature=sampling.temperature,
                    top_p=sampling.top_p,
                    top_k=sampling.top_k,
                    max_tokens=sampling.max_tokens,
                )
            )
            return await invoke(graph, invocation)

        # Asked to join the party: answer it plainly (companions-001).
        invite = await self._invitation(world_id, attempt, reactor_id, names)
        # One task (and graph thread) per attempt and reactor, so a reactor's
        # replies to several attempts run side by side and resume apart.
        result = await _attempt(
            derive_task_id(run_id, f"reaction:{attempt.id.hex}", reactor_id), invite
        )
        if result["proposal"]["reacted"]:
            first = Reaction.model_validate(result["proposal"]["reaction"])
            again = await self._repeats_answered(first, answered)
            if again is not None:
                # The second answer stands, repeat or not.
                result = await _attempt(
                    derive_task_id(run_id, f"reaction:again:{attempt.id.hex}", reactor_id),
                    again if invite is None else f"{invite} {again}",
                )
        await self._remember_intention(world_id, reactor_id, result.get("raw_response"))
        if not result["proposal"]["reacted"]:
            return None
        reaction = Reaction.model_validate(result["proposal"]["reaction"])
        places = {loc.id: loc for loc in (await self._world_view(world_id)).locations}
        return reaction.model_copy(
            update={"action": with_route(reaction.action, sealed.locations.get(reactor_id), places)}
        )

    async def _invitation(
        self, world_id: UUID, attempt: Attempt, reactor_id: UUID, names: Mapping[UUID, str]
    ) -> str | None:
        """The note for a character a party hero asks to join (None otherwise):
        a hero of a combat story, a party with room, someone not in it yet."""
        if not is_invitation(attempt.observable_summary):
            return None
        async with self._factory() as uow:
            roster = await uow.party.list_for_world(world_id)
        linked = {m.character_id for m in roster if m.character_id is not None}
        if attempt.actor_character_id not in linked or reactor_id in linked:
            return None
        if len(roster) >= MAX_PARTY_SIZE or party_name_key(names.get(reactor_id, "")) in {
            m.name_key for m in roster
        }:
            return None
        return invitation_note(names.get(attempt.actor_character_id, "The hero"))

    async def _join_invited(
        self,
        world_id: UUID,
        attempts: Sequence[Attempt],
        reactions: Sequence[Reaction],
    ) -> list[str]:
        """Characters who said a plain yes to a party hero's invitation join
        the party, linked to themselves (their own deeds then roll)."""
        by_id = {a.id: a for a in attempts}
        joined: list[str] = []
        for reaction in reactions:
            attempt = by_id.get(reaction.attempt_id)
            action = reaction.action
            if (
                attempt is None
                or not isinstance(action, CommunicateAction)
                or not is_invitation(attempt.observable_summary)
                or not accepts(action.topic)
            ):
                continue
            async with self._factory() as uow:
                roster = await uow.party.list_for_world(world_id)
                linked = {m.character_id for m in roster if m.character_id is not None}
                if attempt.actor_character_id not in linked:
                    continue
                if reaction.reactor_character_id in linked or len(roster) >= MAX_PARTY_SIZE:
                    continue
                who = await uow.characters.get(reaction.reactor_character_id)
                card = await _card_of(uow, who, self._cards)
            words = " ".join([card.appearance, card.personality, card.background])
            async with self._factory() as uow:
                result = await recruit_companion(
                    uow,
                    self._dnd_tables(),
                    world_id,
                    who.name,
                    companion_description(words, self._dnd_tables()),
                    character_id=who.id,
                )
            if result.joined:
                joined.append(result.member.name)
        return joined

    async def _resolve_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        members: list[Intent],
        runtime: PhaseRuntime,
    ) -> tuple[Resolution, dict[str, int]]:
        """Hybrid resolution with an audited resolver call when ambiguous."""

        async with self._factory() as uow:
            characters = await uow.characters.list_for_world(world_id)
            locations = await uow.locations.list_for_world(world_id)
            items = await uow.inventory.list_for_world(world_id)
            hooks = await uow.narrative.list_hooks_for_world(world_id)
        live_versions = {f"character:{c.id}": c.version for c in characters}
        notes = scene_surroundings(members, characters, locations, items, hooks)
        task_run_id = derive_task_id(run_id, "resolver", scene.id)
        spec = ManifestSpec(
            role="resolver",
            profile=runtime.profiles["resolver"],
            prompt_version=RESOLVER_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            sources=[],
            budgets={},
            tokens={},
            dropped=[],
            pin_profile_id=runtime.pin_id,
            pin_profile_revision=runtime.pin_revision,
        )
        traced = TracedGateway(runtime.gateways["resolver"], self._traces, spec)
        invocation = GraphInvocation(
            graph_name="resolve",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=sealed.snapshot_id,
            scene_id=scene.id,
            role="resolver",
            profile_version=traced.profile.version,
            prompt_version=RESOLVER_PROMPT_VERSION,
            input={
                "intents_json": [i.model_dump(mode="json") for i in members],
                "characters_json": [c.model_dump(mode="json") for c in characters],
                "locations_json": [loc.model_dump(mode="json") for loc in locations],
                "expected_versions": live_versions,
                "surroundings": notes,
                "open_hook_ids": [str(h.id) for h in hooks if h.status != NarrativeStatus.CLOSED],
                "carried": {
                    str(c.id): [item_label(i) for i in items if i.owner_id == c.id]
                    for c in characters
                },
            },
        )
        sampling = runtime.sampling
        graph = build_resolve_graph(
            ResolverGraphDeps(
                gateway=traced,
                profile=runtime.profiles["resolver"],
                system_template=load_resolver_prompt(),
                temperature=sampling.temperature,
                top_p=sampling.top_p,
                top_k=sampling.top_k,
                max_tokens=role_max_tokens(sampling.max_tokens, "resolver"),
            )
        )
        result = await invoke(graph, invocation)
        return Resolution.model_validate(result["proposal"]["resolution"]), live_versions

    def _perceive_scene(
        self,
        world_id: UUID,
        sealed: SealedPhase,
        scene: Scene,
        members: list[Intent],
        names: Mapping[UUID, str],
        reactions: Sequence[Reaction] = (),
        outcome: str | None = None,
    ) -> tuple[list[ObservationSpec], list[MemorySpec]]:
        participant_ids = [p.character_id for p in scene.participants]
        events: list[tuple[UUID, ObservableEvent]] = []
        for intent in sorted(members, key=lambda i: str(i.id)):
            summary = _summarize(intent.action, names, intent.author_character_id)
            if isinstance(intent.action, InteractAction) and outcome:
                # Everyone present sees whether the effort worked.
                summary = f"{summary}: {_OUTCOME_WORDS.get(outcome, outcome)}"
            facts = [
                PerceivedFact(
                    key=f"attempt:{intent.action.family.value}",
                    value=_clip(summary),
                    visibility=FactVisibility.SCENE,
                    channel=FactChannel.SIGHT,
                )
            ]
            disclosures: list[Disclosure] = []
            if isinstance(intent.action, CommunicateAction):
                disclosures.append(
                    Disclosure(
                        fact_key=f"attempt:{intent.action.family.value}",
                        recipient_ids=[intent.action.target_character_id],
                    )
                )
            events.append(
                (
                    intent.id,
                    ObservableEvent(
                        event_id=uuid4(),
                        world_id=world_id,
                        location_id=sealed.locations[intent.author_character_id],
                        participant_ids=participant_ids,
                        facts=facts,
                        disclosures=disclosures,
                    ),
                )
            )
        # Replies are perceived like the attempts they answer: without them
        # a character remembers asking but never what was said back.
        for reaction in sorted(reactions, key=lambda r: str(r.id)):
            reactor = reaction.reactor_character_id
            if reaction.action.family in _SILENT_REPLIES or reactor not in sealed.locations:
                continue
            key = f"reply:{reaction.action.family.value}"
            reply_disclosures: list[Disclosure] = []
            if isinstance(reaction.action, CommunicateAction):
                reply_disclosures.append(
                    Disclosure(fact_key=key, recipient_ids=[reaction.action.target_character_id])
                )
            events.append(
                (
                    reaction.id,
                    ObservableEvent(
                        event_id=uuid4(),
                        world_id=world_id,
                        location_id=sealed.locations[reactor],
                        participant_ids=participant_ids,
                        facts=[
                            PerceivedFact(
                                key=key,
                                value=_clip(_reply_summary(reaction.action, names, reactor)),
                                visibility=FactVisibility.SCENE,
                                channel=FactChannel.SIGHT,
                            )
                        ],
                        disclosures=reply_disclosures,
                    ),
                )
            )
        observations: list[tuple[UUID, PerceivedFact, UUID]] = []
        for observer in sorted(set(participant_ids) | set(sealed.locations)):
            observer_place = sealed.locations.get(observer)
            for source_id, event in events:
                for fact in permitted_facts(event, observer, observer_place):
                    observations.append((observer, fact, source_id))
        specs = [
            observation_spec(observer, [fact], source_id=source_id)
            for observer, fact, source_id in observations
        ]
        memories: list[MemorySpec] = []
        for participant in sorted(set(participant_ids)):
            own_intents = {i.id for i in members if i.author_character_id == participant}
            seen_by_participant = [
                index
                for index, (observer, _fact, _source) in enumerate(observations)
                if observer == participant
            ]
            own = next(
                (i for i in seen_by_participant if observations[i][2] in own_intents),
                seen_by_participant[0] if seen_by_participant else None,
            )
            own_summary = next(
                (
                    _summarize(i.action, names, i.author_character_id)
                    for i in members
                    if i.author_character_id == participant
                ),
                "the scene unfolds",
            )
            memories.append(
                MemorySpec(
                    owner_id=participant,
                    text=f"{names.get(participant, '?')} remembers: {own_summary}",
                    observation_index=own,
                )
            )
        return specs, memories

    def _dnd_tables(self) -> DataTables:
        """Vendored SRD tables, loaded once (only when a party exists)."""
        if self._dnd_data is None:
            self._dnd_data = load_data(DND_DATA_DIR)
        return self._dnd_data

    async def _narrate_scene(
        self,
        world_id: UUID,
        run_id: UUID,
        scene: Scene,
        event_id: UUID,
        quiet: bool = False,
        over_budget: bool = False,
        *,
        runtime: PhaseRuntime,
    ) -> str:
        """Narrate one committed scene; failures never fail the phase.

        Quiet non-party phases and over-budget phases skip the model
        and store structured fallback beats directly: same canon, no
        call. Party scenes always narrate because combat and recruit
        tags live in model-authored beats.

        Structured narration mode (world config ``narration.mode`` set
        to ``"structured"``) applies only to roster-free scenes: with
        no party roster present it takes the same fallback-beat path
        without issuing a narrator call and reports ``"structured"``
        instead of a provider outcome. Like the quiet/over-budget and
        failure paths it skips recruit-from-narration and combat-tag
        resolution. Scenes with a roster proceed to the model path;
        the earlier over-budget skip still applies to any scene
        regardless of roster (that behavior is preserved, not widened
        here). The mode is therefore bounded to roster-free scenarios.
        """
        async with self._factory() as uow:
            existing = await uow.scenes.narrations_for_event(event_id)
            observations = await uow.perception.observations_for_event(event_id)
            scene_reactions = await uow.scenes.reactions_for_scene(scene.id)
            scene_intents = [await uow.scenes.get_intent(i) for i in scene.intent_ids]
            characters = await uow.characters.list_for_world(world_id)
            participants = [
                str(p.character_id) for p in (await uow.scenes.get_scene(scene.id)).participants
            ]
            # The party's sheets and rules go only to a scene the party is in:
            # someone waiting at the market far from the fight gets plain
            # narration, as in a story without fights.
            roster = party_in_scene(await uow.party.list_for_world(world_id), participants)
            # A fight that is on: the narrator strikes its foes, never respawns them.
            fight = await uow.events.latest_fight(world_id) if roster else None
            scene_index = (await uow.phases.get_run(run_id)).absolute_index if roster else 0
            pools = await uow.monsters.list_for_world(world_id) if fight is not None else []
            foes = (
                foes_on(fight.absolute_index, scene_index, fight_keys(fight.summary), pools)
                if fight is not None
                else []
            )
            fight_over = (
                fight_over_line(fight.absolute_index, scene_index, fight_keys(fight.summary), pools)
                if fight is not None
                else None
            )
            config = await uow.worlds.get_config(world_id)
            scene_place = await _event_place(uow, event_id)
            place_name = scene_place.name if scene_place is not None else None
            # Journeys this scene set out on (their travellers have not arrived).
            setting_off = [
                a
                for a in await uow.activities.list_active_for_world(world_id)
                if (a.direct_step_key or "").startswith(f"journey:{scene.id.hex}:")
            ]
            place_names = {loc.id: loc.name for loc in await uow.locations.list_for_world(world_id)}
            previously = await _previously(uow, world_id, event_id)
        if existing:
            return "skipped"
        structured = config.get(NARRATION_MODE_KEY) == NARRATION_MODE_STRUCTURED
        # Reply observations are the characters' memory of reactions; the
        # narrator gets those reactions as citable reaction:<n> facts below.
        sourced = [
            (fact.key, fact.value, obs.source_id)
            for obs in observations
            for fact in obs.facts
            if not fact.key.startswith("reply:")
        ]
        facts = [{"key": key, "value": value} for key, value in dedupe_narration_facts(sourced)]
        names = {c.id: c.name for c in characters}
        # Where the scene happens, so the narrator does not set it elsewhere,
        # and where each participant is by its end: a meeting scene starts
        # where the traveller set out and ends where the others wait.
        ends = whereabouts(characters, participants, place_names)
        setting = scene_place_facts(place_name, ends)
        # A place with a map of its own lists its spots, so the scene is
        # set at one (the story-watch map then stands people there).
        if scene_place is not None and set(ends.values()) <= {scene_place.name}:
            inside = story_spots(config.get(PLACE_MAPS), scene_place.id)
            async with self._factory() as uow:
                last = await _last_spot(uow, world_id, event_id, scene_place.id, inside)
            spots = spots_fact(inside, last)
            if spots is not None:
                setting.append((SPOTS_FACT_KEY, spots))
        if previously is not None:
            setting.append((RECAP_FACT_KEY, previously))
        for key, value in reversed(setting):
            facts.insert(0, {"key": key, "value": value})
        for trip in setting_off:
            facts.append(
                {
                    "key": f"journey:{names.get(trip.character_id, 'someone')}",
                    "value": journey_fact(
                        names.get(trip.character_id, "Someone"),
                        place_names.get(UUID(str(trip.payload["to_location_id"])), "another place"),
                        trip.duration_phases,
                    ),
                }
            )
        # Quoted communicate attempts (a player's "Say" line) are the actor's
        # own speech: dialogue-eligible like quoted reactions.
        facts.extend(attempt_speech_facts(scene_intents, names, participants))
        facts.extend(move_note_facts(scene_intents, names))
        facts.extend(communication_facts(scene_reactions, names, participants))
        async with self._factory() as uow:
            speaker_pronouns = await _pronouns_of(uow, characters, self._cards)
        for fact in facts:
            speaker = fact.get("speaker")
            if speaker and UUID(str(speaker)) in speaker_pronouns:
                fact["speaker_pronouns"] = speaker_pronouns[UUID(str(speaker))]
        # Everyone in the scene, not just speakers: a guess from the name
        # drifted ("her" one beat, "he" the next).
        in_scene = [c for c in characters if str(c.id) in participants]
        if in_scene:
            at = next(
                (i for i, f in enumerate(facts) if f["key"] not in SETTING_FACT_KEYS), len(facts)
            )
            facts.insert(at, {"key": "pronouns", "value": pronoun_line(in_scene, speaker_pronouns)})
        dnd_context: str | None = None
        dnd_sources: list[ManifestSource] = []
        if roster:
            # A blow or spell is the dice's to decide (they roll after the
            # prose), not the resolver's: "it does not work" over a hit read
            # as a contradiction, and a "the dice decide" note was echoed into
            # the prose, so the attempt goes without a verdict (combat-depth-002).
            for fact in facts:
                value = str(fact.get("value", ""))
                if fact["key"] == "attempt:interact" and looks_like_deed(value):
                    for words in _OUTCOME_WORDS.values():
                        if value.endswith(f": {words}"):
                            fact["value"] = value[: -len(words) - 2]
                            break
            tables = self._dnd_tables()
            today = split_absolute(scene_index)[0]
            summaries = {
                member.name_key: build_sheet_summary(tables, long_rest(member.sheet, today))
                + slots_line(tables, long_rest(member.sheet, today), today)
                for member in roster
            }
            facts.extend(
                {"key": f"dnd-sheet:{key}", "value": summary} for key, summary in summaries.items()
            )
            if foes:
                facts.append({"key": "dnd-foes", "value": foes_line(foes)})
            elif fight_over is not None:
                facts.append({"key": "dnd-foes", "value": fight_over})
            fallen = down_line(
                [
                    m.name
                    for m in roster
                    if (woke := long_rest(m.sheet, today).hp) is not None and woke.current <= 0
                ]
            )
            if fallen is not None:
                facts.append({"key": "dnd-down", "value": fallen})
            dnd_context = (
                dnd_party_prompt([long_rest(m.sheet, today) for m in roster], tables)
                + "\n"
                + dnd_story_rules_text()
            )
            dnd_sources = [
                ManifestSource(
                    source_id=f"dnd-sheet:{member.name_key}",
                    kind="dnd-sheet",
                    visibility=Visibility.PUBLIC,
                    reason="party sheet",
                )
                for member in roster
            ]
        task_run_id = derive_task_id(run_id, "narrator", scene.id)
        spec = ManifestSpec(
            role="narrator",
            profile=runtime.profiles["narrator"],
            prompt_version=NARRATOR_PROMPT_VERSION,
            world_id=world_id,
            phase_run_id=run_id,
            task_run_id=task_run_id,
            sources=dnd_sources,
            budgets={},
            tokens={},
            dropped=[],
            pin_profile_id=runtime.pin_id,
            pin_profile_revision=runtime.pin_revision,
        )
        traced = TracedGateway(runtime.gateways["narrator"], self._traces, spec)
        invocation = GraphInvocation(
            graph_name="narrate",
            graph_version="v1",
            task_run_id=task_run_id,
            world_id=world_id,
            phase_run_id=scene.phase_run_id,
            snapshot_id=scene.snapshot_id,
            scene_id=scene.id,
            role="narrator",
            profile_version=traced.profile.version,
            prompt_version=NARRATOR_PROMPT_VERSION,
            input={
                "event_id": str(event_id),
                "event_committed": True,
                "audience_ids": participants,
                "visible_facts": facts,
                "beats_budget": scene.beat_budget,
                "dnd_context": dnd_context,
            },
        )
        roster_pre = bool(roster)
        if over_budget or (quiet and not roster_pre):
            await self._save_fallback_beats(world_id, scene, event_id, facts, source="fallback")
            if roster_pre:
                # The party's own blows still roll without the storyteller.
                await self._resolve_combat_tags(world_id, run_id, scene, event_id, [])
            return "fallback"
        if structured and not roster_pre:
            # Configured structured narration, not a provider outcome:
            # same beats as the quiet path, no narrator call issued and
            # no model-call row traced.
            await self._save_fallback_beats(world_id, scene, event_id, facts, source="structured")
            return "structured"
        try:
            sampling = runtime.sampling
            graph = build_narration_graph(
                NarratorGraphDeps(
                    gateway=traced,
                    profile=runtime.profiles["narrator"],
                    system_template=load_narrator_prompt(),
                    temperature=sampling.temperature,
                    top_p=sampling.top_p,
                    top_k=sampling.top_k,
                    max_tokens=sampling.max_tokens,
                )
            )
            result = await invoke(graph, invocation)
        except Exception:
            # No beats to atomize with; record the failure best-effort so
            # replays report it instead of an unknown source. A failed
            # status write degrades to the old behavior (NULL status).
            try:
                async with self._factory() as uow:
                    await uow.scenes.save_narration_status(scene.id, "failed")
                    await uow.commit()
            except Exception:
                # Best-effort only: failures here must never fail the phase.
                pass
            if roster_pre:
                # The storyteller failed, but the party's own blows still roll.
                await self._resolve_combat_tags(world_id, run_id, scene, event_id, [])
            return "failed"
        source = "narrated" if not result["proposal"]["fallback"] else "fallback"
        async with self._factory() as uow:
            for beat_json in result["proposal"]["beats"]:
                await uow.scenes.save_narration(NarrationBeat.model_validate(beat_json))
            await uow.scenes.save_narration_status(scene.id, source)
            await uow.commit()
            beat_texts = [
                str(beat_json.get("text", "")) for beat_json in result["proposal"]["beats"]
            ]
        joined = await self._recruit_from_narration(world_id, "\n".join(beat_texts))
        await self._resolve_combat_tags(
            world_id, run_id, scene, event_id, beat_texts, joined=joined
        )
        return source

    async def _save_fallback_beats(
        self,
        world_id: UUID,
        scene: Scene,
        event_id: UUID,
        facts: list[dict[str, str]],
        *,
        source: str,
    ) -> None:
        """Persist deterministic beats with their source, atomically."""
        async with self._factory() as uow:
            for beat in fallback_beats(
                world_id=world_id,
                scene_id=scene.id,
                event_id=event_id,
                visible_facts=facts,
                beats_budget=scene.beat_budget,
            ):
                await uow.scenes.save_narration(beat)
            await uow.scenes.save_narration_status(scene.id, source)
            await uow.commit()

    async def _recruit_from_narration(self, world_id: UUID, text: str) -> list[str]:
        """Resolve RECRUIT tags from narration; replays for members are no-ops."""
        tags = parse_recruit_tags(text)
        if not tags:
            return []
        async with self._factory() as uow:
            if not await uow.party.list_for_world(world_id):
                return []
        joined: list[str] = []
        tables = self._dnd_tables()
        async with self._factory() as uow:
            for tag in tags:
                result = await recruit_companion(uow, tables, world_id, tag.name, tag.desc)
                if result.joined:
                    joined.append(result.member.name)
        return joined

    async def _resolve_combat_tags(
        self,
        world_id: UUID,
        run_id: UUID,
        scene: Scene,
        event_id: UUID,
        beat_texts: list[str],
        *,
        joined: list[str] | None = None,
    ) -> str:
        """Roll tagged combat, persist HP, and record one combat event plus beats.

        The event's summary also carries the rolls in parts (``rolls``), the
        scene they belong under (``scene_event_id``) and the foes in the
        fight (``foes``), so the story log can show each roll under its
        scene; companions who joined in the scene are listed there too.

        Runs after narration is saved and never fails the phase: domain
        contention returns "failed" while unexpected errors stay loud.
        Rolls seed from the narrated event, so the same narration replays
        to the same numbers; the combat event ID derives from it too, so
        a double resolve collides instead of double-applying HP.
        """
        text = "\n".join(beat_texts)
        async with self._factory() as uow:
            roster = await uow.party.list_for_world(world_id)
            if not roster:
                return "no-party"
            live_monsters = await uow.monsters.list_for_world(world_id)
            run = await uow.phases.get_run(run_id)
            # What the linked heroes tried this scene, in their own words: a
            # plain attack or spell rolls even when the storyteller did not
            # tag it (combat-depth-002).
            heroes = {
                member.character_id: member.name_key
                for member in roster
                if member.character_id is not None
            }
            deeds: list[Deed] = []
            hero_here = False
            grant = await uow.roles.get_for_world(world_id)
            chooses = chooser_keys(roster, grant.character_id if grant is not None else None)
            participants = {
                str(p.character_id) for p in (await uow.scenes.get_scene(scene.id)).participants
            }
            for intent_id in scene.intent_ids:
                intent = await uow.scenes.get_intent(intent_id)
                hero_here = hero_here or intent.author_character_id in heroes
                action = intent.action
                if isinstance(action, InteractAction) and intent.author_character_id in heroes:
                    deeds.append(Deed(key=heroes[intent.author_character_id], text=action.attempt))
            # The fight that is on (before this scene): newcomers of a kind
            # still standing join it instead of replacing it.
            fight = await uow.events.latest_fight(world_id)
            fighting = (
                [
                    foe.name_key
                    for foe in foes_on(
                        fight.absolute_index,
                        run.absolute_index,
                        fight_keys(fight.summary),
                        live_monsters,
                    )
                ]
                if fight is not None
                else []
            )
        tables = self._dnd_tables()
        story_day = split_absolute(run.absolute_index)[0]
        digest = hashlib.sha256(str(event_id).encode()).digest()[:8]
        seed = int.from_bytes(digest, "big") & ((1 << 63) - 1)
        try:
            for _ in range(2):
                report = resolve_narration_tags(
                    text,
                    [member.sheet for member in roster],
                    tables,
                    random.Random(seed).random,
                    live=[
                        MonsterState(
                            key=monster.name_key,
                            name=monster.name,
                            hp_current=monster.hp_current,
                            hp_max=monster.hp_max,
                            ac=monster.ac,
                        )
                        for monster in live_monsters
                    ],
                    day=story_day,
                    fighting=fighting,
                    deeds=deeds,
                    chooses=chooses,
                    strike_back=hero_here,
                    present=present_keys(roster, participants, hero_here),
                )
                if not report.outcomes and not report.unresolved and not joined:
                    return "no-tags"
                try:
                    async with self._factory() as uow:
                        by_key = {member.name_key: member for member in roster}
                        # HP, conditions, spent slots, XP and levels in one save each.
                        for key in sorted(report.sheets):
                            member = by_key[key]
                            await uow.party.save_sheet(
                                member.id, report.sheets[key], member.version
                            )
                        pools = {monster.name_key: monster for monster in live_monsters}
                        for key in sorted(report.monsters):
                            result = report.monsters[key]
                            pool = pools.get(key)
                            if pool is None:
                                await uow.monsters.add(
                                    Monster(
                                        id=new_monster_id(),
                                        world_id=world_id,
                                        name_key=key,
                                        name=result.name,
                                        hp_current=result.hp_current,
                                        hp_max=result.hp_max,
                                        ac=result.ac,
                                    )
                                )
                            elif (
                                pool.hp_current != result.hp_current
                                or pool.hp_max != result.hp_max
                                or result.spawned
                            ):
                                await uow.monsters.save_hp(pool.id, result.hp_current, pool.version)
                        combat_id = derive_combat_event_id(event_id)
                        sequence = await uow.events.max_sequence(world_id) + 1
                        involved = {
                            by_key[key].id
                            for outcome in report.outcomes
                            for key in (outcome.attacker_key, outcome.target_key)
                            if key is not None and key in by_key
                        }
                        log = " | ".join(o.text for o in report.outcomes)[:512]
                        await uow.events.append_event(
                            WorldEvent(
                                id=combat_id,
                                world_id=world_id,
                                sequence=sequence,
                                event_type=EventType.ACTION_RESOLVED,
                                absolute_index=run.absolute_index,
                                phase_run_id=run_id,
                                participant_ids=sorted(involved, key=str),
                                summary={
                                    "tags": str(len(report.outcomes)),
                                    "unresolved": str(len(report.unresolved)),
                                    "deeds": str(report.deeds),
                                    "helped": str(report.helped),
                                    "scene_event_id": str(event_id),
                                    "rolls": combat_rolls_json(report.outcomes, joined or []),
                                    # The fight that is on goes on: its foes
                                    # plus whoever this scene brought in.
                                    **(
                                        {
                                            "foes": json.dumps(
                                                list(dict.fromkeys(fighting + report.foes))
                                            )
                                        }
                                        if report.foes
                                        else {}
                                    ),
                                },
                                random_seed=seed,
                                random_algorithm="seeded-d20-v1",
                                random_result=log or None,
                            )
                        )
                        for beat in report.beats:
                            await uow.scenes.save_narration(
                                NarrationBeat(
                                    id=new_narration_id(),
                                    world_id=world_id,
                                    scene_id=scene.id,
                                    source_event_id=combat_id,
                                    cited_fact_keys=list(beat.cited),
                                    text=beat.text,
                                )
                            )
                        await uow.commit()
                    return "resolved"
                except DomainError as exc:
                    if exc.code is not ErrorCode.VERSION_CONFLICT:
                        raise
                    async with self._factory() as uow:
                        roster = await uow.party.list_for_world(world_id)
            return "failed"
        except DomainError:
            return "failed"

    async def _duplicate_report(self, world_id: UUID, run_id: UUID) -> Stage1PhaseReport:
        """Rebuild the stored report for a completed run (no new canon)."""
        async with self._factory() as uow:
            run = await uow.phases.get_run(run_id)
            snapshot = await uow.phases.get_snapshot(derive_snapshot_id(run_id))
            characters = [c.character_id for c in snapshot.characters]
            intents = [
                await uow.scenes.get_intent(derive_intent_id(world_id, snapshot.id, c))
                for c in characters
            ]
            view_world = await uow.worlds.get(world_id)
            view_chars = await uow.characters.list_for_world(world_id)
            view_locs = await uow.locations.list_for_world(world_id)
        scenes = assemble_scenes(
            intents,
            WorldView(world=view_world, characters=view_chars, locations=view_locs),
            world_id=world_id,
            phase_run_id=run_id,
            snapshot_id=snapshot.id,
        )
        outcomes: list[SceneOutcome] = []
        async with self._factory() as uow:
            for scene in scenes:
                stored = await uow.scenes.get_scene(scene.id)
                assert stored.event_id is not None
                resolution = await uow.scenes.get_resolution(scene.id)
                beats = await uow.scenes.narrations_for_event(stored.event_id)
                if stored.narration_status is not None:
                    narration = stored.narration_status
                elif beats:
                    # Legacy rows predate the record: beats without source.
                    narration = "unknown"
                else:
                    # No beats and no record: attempt failure and beat
                    # availability stay distinct from an unknown source.
                    narration = "missing"
                outcomes.append(
                    SceneOutcome(
                        scene_id=scene.id,
                        event_id=stored.event_id,
                        resolution_outcome=resolution.outcome.value,
                        narration=narration,
                    )
                )
        return Stage1PhaseReport(
            run_id=run_id,
            world_id=world_id,
            absolute_index=run.absolute_index,
            snapshot_id=snapshot.id,
            scenes=outcomes,
            duplicate=True,
            quiet=is_quiet_phase(intent.action.family for intent in intents),
        )
