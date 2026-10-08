"""Stage 0 request/response DTOs (owned by S0-API-001).

Never ORM structures: every model here is an explicit projection of a
domain record. UUIDs render as strings; operational timestamps are
ISO-8601 UTC.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.autoplay import (
    DEFAULT_BEAT_LIMIT,
    MAX_BEAT_LIMIT,
    MAX_DELAY_SECONDS,
    PRESENCE_GRACE_SECONDS,
)
from worldsim.domain.enums import PhaseName


class HealthLiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"


class DependencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: Literal["ok", "degraded", "failed"]
    detail: str = ""


class ReadyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "degraded"]
    version: str
    environment: str
    migration_head: str | None
    schema_version: int
    checks: list[DependencyCheck]


class WorldResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    status: str
    day: int
    phase: PhaseName
    absolute_index: int
    seed_version: str
    version: int


class ClockResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    day: int
    phase: PhaseName
    absolute_index: int


class CurrentPhaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    absolute_index: int
    day: int
    phase: PhaseName
    run_id: UUID | None
    run_state: str | None


class EventEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    id: UUID
    event_type: str
    absolute_index: int
    phase_run_id: UUID
    effect_count: int


class EventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: list[EventEntry]
    next_after: int


class SeedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    seed_version: str
    content_hash: str
    duplicate: bool


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class ReconcileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tasks_requeued: int
    outbox_requeued: int
    open_run_id: UUID | None
    open_state: str | None


class TaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    kind: str
    state: str
    owner: str | None
    attempt: int | None
    max_attempts: int | None
    expires_at: datetime | None


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    request_id: str
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: ErrorDetail


class CharacterSummary(BaseModel):
    """Stage 1 character listing (owned by S1-API-001)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    life_status: str
    location_id: UUID


class CharacterDetail(BaseModel):
    """Stage 1 character view; card excerpt only for self or watcher."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    life_status: str
    location_id: UUID
    card: dict[str, object] | None = None
    state: dict[str, object] | None = None


class ParticipantView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    role: str


class IntentView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    author_character_id: UUID
    family: str
    detail: dict[str, object] | None = None


class AttemptView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    actor_character_id: UUID
    observable_summary: str
    status: str


class ReactionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    reactor_character_id: UUID
    family: str
    detail: dict[str, object] | None = None


class ResolutionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: str
    resolver: str
    rationale: str


class SceneDetail(BaseModel):
    """Stage 1 scene view scoped to the caller perspective (S1-API-001)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    phase_run_id: UUID
    status: str
    beat_budget: int
    event_id: UUID | None = None
    participants: list[ParticipantView] = Field(default_factory=list)
    intents: list[IntentView] = Field(default_factory=list)
    attempts: list[AttemptView] = Field(default_factory=list)
    reactions: list[ReactionView] = Field(default_factory=list)
    resolution: ResolutionView | None = None


class SceneSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    status: str
    event_id: UUID | None = None
    participant_ids: list[UUID] = Field(default_factory=list)


class BeatView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    speaker_id: UUID | None = None
    kind: str
    text: str
    source_event_id: UUID
    cited_fact_keys: list[str] = Field(default_factory=list)


class ModelRunView(BaseModel):
    """Watcher-only model audit view: metadata, never raw hidden content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: UUID
    role: str
    profile: str
    status: str
    actor_id: UUID | None = None
    task_run_id: UUID | None = None
    manifest_id: UUID | None = None
    rendered_hash: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    error_code: str | None = None
    finish_reason: str | None = None
    reasoning_tokens: int = 0
    content_type: str | None = None
    content_length: int | None = None
    reasoning_only: bool | None = None
    max_tokens: int | None = None
    pin_profile_id: str | None = None
    pin_profile_revision: int | None = None
    budgets: dict[str, int] = Field(default_factory=dict)
    attempts: list[dict[str, Any]] = Field(default_factory=list)


class Stage1AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    absolute_index: int = Field(ge=1)
    player_intents: dict[str, dict[str, object]] = Field(default_factory=dict)


class Stage1SceneOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: UUID
    event_id: UUID
    resolution_outcome: str
    narration: str


class Stage1AdvanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    world_id: UUID
    absolute_index: int
    snapshot_id: UUID
    scenes: list[Stage1SceneOutcome] = Field(default_factory=list)
    duplicate: bool = False
    quiet: bool = False


class RunIdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID


class PartyBeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    name: str = Field(min_length=1, max_length=128)
    race: str = Field(default="human", max_length=64)
    character_class: str = Field(default="fighter", max_length=64)
    level: int = Field(default=1, ge=1, le=20)
    stats: dict[str, int] | None = None
    character_id: UUID | None = None


class PartyMemberView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    name: str
    level: int
    character_class: str
    hp_current: int | None = None
    hp_max: int | None = None
    conditions: list[str] = Field(default_factory=list)
    character_id: UUID | None = None
    version: int


class ActivityStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    kind: str = Field(max_length=32)
    duration_phases: int | None = Field(default=None, ge=1, le=100)
    to_location_id: UUID | None = None
    skill: str | None = Field(default=None, max_length=64)


class ItemGiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    item_key: str = Field(max_length=64)
    owner_id: UUID | None = None
    quantity: int = Field(default=1, ge=1)


class ItemTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    to_owner_id: UUID | None = None


class ItemView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    item_key: str
    owner_id: UUID | None
    quantity: int
    version: int
    #: Display name: the item's own, else the catalog's, else its key.
    name: str = ""
    description: str = ""


class ItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    owner_id: UUID | None
    members: list[ItemView] = Field(default_factory=list)


class SkillView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    skill_key: str
    progress: int
    sessions: int
    version: int


class SkillListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    members: list[SkillView] = Field(default_factory=list)


class ActivityView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    character_id: UUID
    kind: str
    status: str
    start_absolute: int
    duration_phases: int
    progress_phases: int
    from_location_id: UUID | None = None
    to_location_id: UUID | None = None
    route_id: UUID | None = None
    effective_progress_phases: int | None = None
    version: int


class ActivityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    members: list[ActivityView] = Field(default_factory=list)


class RelationshipEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    source_id: UUID
    target_id: UUID
    dimension: str = Field(max_length=16)
    delta: int = Field(ge=-10, le=10)
    note: str = Field(default="", max_length=512)


class RelationshipView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    source_id: UUID
    target_id: UUID
    direction: str
    trust: int
    affection: int
    respect: int
    summary: str
    version: int


class RelationshipListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    members: list[RelationshipView] = Field(default_factory=list)


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    speaker_id: UUID
    proposition: str = Field(min_length=1, max_length=1024)
    audience_location_id: UUID | None = None
    refutes_claim_id: UUID | None = None


class ClaimView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    speaker_id: UUID
    audience_location_id: UUID | None
    proposition: str
    refutes_claim_id: UUID | None
    version: int


class ClaimListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    viewer_id: UUID
    members: list[ClaimView] = Field(default_factory=list)


class BeliefView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    holder_id: UUID
    proposition: str
    confidence: float
    last_touched_absolute: int
    version: int


class BeliefListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    holder_id: UUID
    members: list[BeliefView] = Field(default_factory=list)


class RoleSelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    role: str = Field(max_length=16)
    character_id: UUID | None = None


class RoleGrantView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    role: str
    character_id: UUID | None
    granted_absolute: int
    version: int


class DirectorProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    kind: str = Field(pattern="^(hook|arc)$")
    title: str = Field(min_length=1, max_length=128)
    purpose: str = Field(default="", max_length=1024)
    requested_powers: list[str] = Field(default_factory=list)
    participant_ids: list[UUID] = Field(default_factory=list)


class DirectorProposalView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    kind: str
    title: str
    reason: str


class DeityOverrideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    stamina: int | None = Field(default=None, ge=0, le=100)
    mana: int | None = Field(default=None, ge=0, le=100)
    life_status: str | None = Field(default=None, max_length=16)
    conditions: list[str] | None = None
    retcon: bool = False


class DeityOverrideView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    world_id: UUID
    character_id: UUID
    retcon: bool


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    event_id: UUID
    event_type: str
    absolute_index: int
    snippet: str | None = None


class TimelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    entries: list[TimelineEntry] = Field(default_factory=list)
    total: int
    next_after: int
    has_more: bool


class MapRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    to_location_id: UUID
    duration_phases: int


class MapPlace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    region: str
    discovered: bool
    routes: list[MapRoute] = Field(default_factory=list)
    occupants: list[str] = Field(default_factory=list)
    occupant_ids: list[UUID] = Field(default_factory=list)


class MapResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    places: list[MapPlace] = Field(default_factory=list)


class DiaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    phase: int
    text: str


class DiaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    observations: list[DiaryEntry] = Field(default_factory=list)
    memories: list[DiaryEntry] = Field(default_factory=list)
    summaries: list[DiaryEntry] = Field(default_factory=list)
    digests: list[DiaryEntry] = Field(default_factory=list)


class HookView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: str


class ArcView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    title: str
    status: str


class HookListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    hooks: list[HookView] = Field(default_factory=list)
    arcs: list[ArcView] = Field(default_factory=list)


class OperationsStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    open_run_id: UUID | None
    open_run_state: str | None
    pending_outbox: int
    total_events: int


class PartyRosterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    members: list[PartyMemberView] = Field(default_factory=list)


class MacroEffectView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    detail: str
    event_id: UUID | None = None
    target_ids: list[UUID] = Field(default_factory=list)


class MacroInterruptionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    at_absolute: int
    reason: str
    detail: str


class MacroRunView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    start_absolute: int
    end_absolute: int
    resolution: str
    state: str
    effects: list[MacroEffectView] = Field(default_factory=list)
    interruptions: list[MacroInterruptionView] = Field(default_factory=list)


class MacroRunsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    runs: list[MacroRunView] = Field(default_factory=list)


class LineageLinkView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_id: UUID
    parent_name: str
    child_id: UUID
    child_name: str
    birth_absolute: int


class LineageRecordView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    name: str
    birth_absolute: int
    death_absolute: int | None = None
    life_status: str
    succession_eligible: bool


class LineageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    links: list[LineageLinkView] = Field(default_factory=list)
    records: list[LineageRecordView] = Field(default_factory=list)


class FocusAssignmentView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slot: str
    version: int
    from_character_id: UUID | None = None
    from_name: str | None = None
    to_character_id: UUID
    to_name: str
    effective_absolute: int
    reason: str


class FocusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    assignments: list[FocusAssignmentView] = Field(default_factory=list)


class EraView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    era_id: UUID
    owner_id: UUID
    start_absolute: int
    end_absolute: int
    text: str
    source_ids: list[str] = Field(default_factory=list)
    version: int


class ErasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    eras: list[EraView] = Field(default_factory=list)


class EndingView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    satisfied: bool
    evaluated_absolute: int
    window_start_absolute: int
    evidence_event_ids: list[str] = Field(default_factory=list)
    detail: str


class EndingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    endings: list[EndingView] = Field(default_factory=list)


class MacroAdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    day: int = Field(ge=1)
    resolution: str = Field(min_length=1, max_length=16)


class MacroAdvanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    state: str
    start_absolute: int
    end_absolute: int
    event_ids: list[UUID] = Field(default_factory=list)
    duplicate: bool


class EraComposeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    owner_id: UUID
    start_absolute: int = Field(ge=0)
    end_absolute: int = Field(ge=1)


class EndingsEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    at_absolute: int = Field(ge=0)


class FocusAssignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    slot: str = Field(min_length=1, max_length=16)
    to_character_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    effective_absolute: int = Field(ge=0)
    from_character_id: UUID | None = None


class ScheduleCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schedule_id: UUID
    status: str


class CharacterCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    name: str = Field(min_length=1, max_length=128)
    location_id: UUID
    appearance: str = Field(default="", max_length=2000)
    personality: str = Field(default="", max_length=2000)
    background: str = Field(default="", max_length=2000)
    pronouns: str = Field(default="", max_length=40)


class PartyLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    character_id: UUID
    expected_version: int = Field(ge=0)


class ChronicleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence: int
    event_id: UUID
    event_type: str
    title: str
    text: str | None = None
    participant_ids: list[UUID] = Field(default_factory=list)
    location_id: UUID | None = None
    #: The spot inside the place the scene's prose names, when the place
    #: has a map of its own.
    spot_key: str | None = None
    scene_id: UUID | None = None
    absolute_index: int
    revision: int = 0
    #: Everyone in the scene only waited or rested (feeds fold these together).
    idle: bool = False


class ChronicleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    entries: list[ChronicleEntry] = Field(default_factory=list)
    next_after: int
    has_more: bool
    watermark: int


class PresentationCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str
    character_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list)


class MapAnchorView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    location_id: UUID
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class MapRoadLineView(BaseModel):
    """A road as drawn on the map art: both ends included, map fractions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_location_id: UUID
    to_location_id: UUID
    by: str = "road"
    points: list[tuple[float, float]] = Field(default_factory=list)


class MapManifestView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    version: int
    schematic: bool
    asset_id: UUID | None = None
    anchors: list[MapAnchorView] = Field(default_factory=list)
    #: Roads drawn on the art; empty means straight lines between anchors.
    roads: list[MapRoadLineView] = Field(default_factory=list)


class PlaceSpotView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    name: str
    kind: str = ""
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class PlaceMapView(BaseModel):
    """A place's own map in a story: its art and the spots on it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location_id: UUID
    asset_id: UUID
    spots: list[PlaceSpotView] = Field(default_factory=list)


class CastEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    name: str
    life_status: str
    location_id: UUID
    portrait_asset_id: UUID | None = None
    #: On an imported portrait: the parts its cards and its round tokens
    #: show, [x, y, w, h] fractions of the picture; absent on painted ones.
    portrait_frame: list[float] | None = None
    face_frame: list[float] | None = None


class RumourView(BaseModel):
    """An open opening as the viewer would hear it: word around the vale."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hook_id: UUID
    title: str
    purpose: str = ""
    since_index: int = 0


class PlaceArtView(BaseModel):
    """A place's own scene art (newest background asset)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    location_id: UUID
    asset_id: UUID


class SceneArtView(BaseModel):
    """A painted moment of a scene; ``asset_id`` once the painting is done."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    picture_id: UUID
    scene_id: UUID
    #: turning, arrival, meeting, settled or manual.
    moment: str
    #: A short headline for the moment; older pictures have none.
    title: str | None = None
    caption: str
    #: pending (being painted), ready or failed.
    status: str
    asset_id: UUID | None = None
    #: The beat it was painted for (day and time of day follow from it).
    phase_index: int = 0
    location_id: UUID | None = None


class PictureCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    name: str
    #: Has a portrait, so the picture keeps their face.
    has_face: bool


class PictureSuggestion(BaseModel):
    """What "Paint this scene" offers before the player edits it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str
    caption: str
    characters: list[PictureCharacter] = Field(default_factory=list)
    place: str | None = None
    #: False when the server has no image machine (painting is refused).
    available: bool
    #: Story settings words added before and after the prompt when painting.
    added_before: str = ""
    added_after: str = ""


class PaintSceneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    prompt: str = Field(min_length=1, max_length=2000)
    caption: str | None = Field(default=None, max_length=400)


class JourneyView(BaseModel):
    """The player character's journey so far and the renown it has earned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    places: int
    people: int
    deeds: int
    settled: int
    renown: int
    level: int
    title: str
    level_floor: int
    next_level_at: int


class PresentationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    day: int
    phase: str
    absolute_index: int
    latest_run_id: UUID | None = None
    open_run_id: UUID | None = None
    run_state: str | None = None
    revision: int
    capabilities: PresentationCapabilities
    manifest: MapManifestView
    #: Places with their own map, among those the viewer can see.
    place_maps: list[PlaceMapView] = Field(default_factory=list)
    cast: list[CastEntry] = Field(default_factory=list)
    activities: list[ActivityView] = Field(default_factory=list)
    recent_event_id: UUID | None = None
    threads: list[str] = Field(default_factory=list)
    #: Open openings this viewer has heard of (the rule characters hear by).
    rumours: list[RumourView] = Field(default_factory=list)
    #: Recently settled ones, with their endings as purpose.
    settled: list[RumourView] = Field(default_factory=list)
    #: The viewing player's journey (players only).
    journey: JourneyView | None = None
    #: Scene art per place, for places that have their own.
    place_art: list[PlaceArtView] = Field(default_factory=list)
    scene_art: list[SceneArtView] = Field(default_factory=list)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID | None = None
    kind: str = Field(min_length=1, max_length=16)
    subject_id: UUID | None = None
    style_pack_version: str = Field(default="anime-saga-v1", max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class JobView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID | None = None
    kind: str
    subject_id: UUID | None = None
    style_pack_version: str
    status: str
    attempt_count: int
    result_asset_id: UUID | None = None
    error: str = ""
    version: int


class AssetView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID | None = None
    kind: str
    subject_id: UUID | None = None
    content_ref: str
    mime: str
    width: int
    height: int
    style_pack_version: str
    subject_visual_version: int
    status: str
    version: int


class EnsureStarterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID


class SimulationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    absolute_index: int
    open_run_id: UUID | None = None
    open_run_index: int | None = None
    open_run_state: str | None = None
    latest_run_id: UUID | None = None
    latest_run_state: str | None = None


class InterventionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(default="world", max_length=32)
    character_ids: list[UUID] = Field(default_factory=list)
    location_ids: list[UUID] = Field(default_factory=list)


class InterventionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    client_request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=2000)
    mode: str = Field(min_length=1, max_length=16)
    scope: InterventionScope = Field(default_factory=InterventionScope)
    effective_at: str = Field(default="next_boundary", max_length=32)


class InterventionStepView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    seq: int
    kind: str
    status: str
    explanation: str = ""
    result_event_id: UUID | None = None
    result_activity_id: UUID | None = None
    result_hook_id: UUID | None = None
    failure_reason: str = ""
    version: int


class InterventionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    status: str
    mode: str
    role: str
    text: str
    client_request_id: str = Field(min_length=1, max_length=128)
    steps: list[InterventionStepView] = Field(default_factory=list)
    failure_reason: str = ""
    version: int


class InterventionEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=2000)
    scope: InterventionScope = Field(default_factory=InterventionScope)
    expected_version: int = Field(ge=0)


class InterventionCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=0)


class SuggestionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    family: str
    title: str
    subtitle: str = ""
    target_character_id: UUID | None = None
    destination_location_id: UUID | None = None
    needs_topic: bool = False
    item_instance_id: UUID | None = None


class ConditionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    kind: str
    public_label: str
    detail: str = ""
    scope_location_ids: list[UUID] = Field(default_factory=list)
    severity: int
    started_absolute: int
    ends_absolute: int
    status: str
    version: int


class ConditionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    conditions: list[ConditionView] = Field(default_factory=list)


class StorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    story_id: UUID
    world_id: UUID
    title: str
    world_name: str
    mode: str
    day: int
    phase: str
    absolute_index: int
    last_played_at: datetime | None = None
    archived: bool = False
    status: str


class StoryDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    story_id: UUID
    world_id: UUID
    title: str
    world_name: str
    mode: str
    day: int
    phase: str
    absolute_index: int
    last_played_at: datetime | None = None
    archived_at: datetime | None = None
    status: str
    metadata_version: int
    #: The world's own picture, kept with the story, and its 16:7 banner
    #: frame [x, y, w, h]; None: the story has no cover.
    cover_asset_id: UUID | None = None
    cover_frame: list[float] | None = None


class StoryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[StorySummary] = Field(default_factory=list)
    next_cursor: str | None = None


class StorySetupView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    story_id: UUID
    world_id: UUID
    schema_version: int
    provenance: str
    payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    created_at: datetime


class StoryPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str | None = Field(default=None, min_length=1, max_length=128)
    cover_asset_id: UUID | None = None
    expected_version: int = Field(ge=1)


class StoryArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)


class StoryDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world: dict[str, Any] | None = None
    cast: list[dict[str, Any]] | None = None
    mode: dict[str, Any] | None = None
    story: dict[str, Any] | None = None
    ai: dict[str, Any] | None = None


class StoryDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: StoryDraftPayload = Field(default_factory=StoryDraftPayload)
    current_step: str = "world"


class StoryDraftPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: StoryDraftPayload
    current_step: str
    expected_version: int = Field(ge=1)


class StoryDraftView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    payload: StoryDraftPayload
    current_step: str
    version: int
    created_at: datetime
    updated_at: datetime
    created_world_id: UUID | None = None


class DraftValidationView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    issues: list[str] = Field(default_factory=list)
    resolved: dict[str, Any] = Field(default_factory=dict)


class PresetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    kind: str
    name: str
    builtin: bool
    readonly: bool
    archived: bool
    current_revision: int
    version: int


class PresetDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    kind: str
    name: str
    builtin: bool
    readonly: bool
    archived_at: datetime | None = None
    current_revision: int
    version: int
    revision: dict[str, Any] = Field(default_factory=dict)


class PresetPublishView(BaseModel):
    """Published revision pinned separately from the Library head.

    `detail` carries the resolved revision payload alongside the
    preset's current head metadata; `published_revision` names exactly
    which revision this publication (or replay) produced, so a caller
    can adopt it unambiguously even after later revisions exist.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    published_revision: int = Field(ge=1)
    detail: PresetDetail


class PresetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    name: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any]


class PresetArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=0)


class PresetRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: dict[str, Any]
    expected_version: int = Field(ge=0)


class EditorDraftView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    preset_id: UUID
    base_revision: int
    fields: dict[str, Any] = Field(default_factory=dict)
    version: int
    updated_at: datetime
    replayed: bool = False
    published_version: int | None = None
    published_revision: int | None = None
    published_hash: str | None = None


class EditorDraftOpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_revision: int = Field(ge=1)


class EditorDraftSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fields: dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(ge=1)


class EditorDraftPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)
    preset_expected_version: int = Field(ge=0)


class EditorDraftCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_version: int = Field(ge=1)


class PreferencesView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operator: str
    gameplay: dict[str, Any] = Field(default_factory=dict)
    accessibility: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    images: dict[str, Any] = Field(default_factory=dict)
    version: int


class PreferencesPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gameplay: dict[str, Any] | None = None
    accessibility: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    images: dict[str, Any] | None = None
    expected_version: int = Field(ge=0)


class ProviderConnectionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    adapter: str
    name: str
    endpoint: str
    credential_env: str | None = None
    has_credential: bool = False
    allow_local_endpoint: bool = False
    config_version: int
    created_at: datetime


class ProviderConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: str
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=512)
    credential_env: str | None = Field(default=None, max_length=128)
    allow_local_endpoint: bool = False


class ProviderConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    credential_env: str | None = Field(default=None, max_length=128)
    allow_local_endpoint: bool | None = None
    expected_version: int = Field(ge=0)


class ProviderProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    connection_id: UUID
    revision: int
    model_id: str
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int
    capabilities: list[str] = Field(default_factory=list)
    created_at: datetime


class ProviderProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1, max_length=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=100)
    max_tokens: int = Field(default=512, ge=1, le=4096)


class ProviderCapabilitiesView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connection_id: UUID
    adapter: str
    supported_parameters: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    probe: dict[str, Any] = Field(default_factory=dict)


class ProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    live: bool = False


class ProviderTestView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str
    reachable: bool = False
    text_ready: str = "unknown"
    detail: str = ""
    tested_at: str = ""
    tested_config_revision: int = 0


class StoryProviderPinView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: UUID
    revision: int
    model_id: str
    adapter: str
    connection_name: str


class StoryProviderEnvironmentView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_profile: str
    adapter: str
    model_id: str | None = None


class StoryProviderView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    story_id: UUID
    world_id: UUID
    pin_state: Literal["none", "ok", "broken"]
    pin: StoryProviderPinView | None = None
    pin_error: str | None = None
    environment: StoryProviderEnvironmentView
    effective_source: Literal["pin", "environment", "unavailable"]
    effective_adapter: str | None = None
    effective_model_id: str | None = None
    effective_revision: int | None = None


class CacheScopeView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: str
    files: int
    description: str


class CacheClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: str


class StoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_id: UUID
    expected_draft_version: int = Field(ge=1)


class StoryCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    story_id: UUID
    world_id: UUID
    role: str
    character_id: UUID | None = None
    replayed: bool = False
    art_registered: int = 0


class AutoplayView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    status: str
    delay_seconds: int
    beats_left: int
    beats_run: int
    stop_reason: str | None = None
    stop_detail: str | None = None
    next_due_at: datetime | None = None
    last_seen_at: datetime | None = None
    presence_grace_seconds: int = PRESENCE_GRACE_SECONDS
    runner_enabled: bool
    version: int


class AutoplayPlayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    delay_seconds: int = Field(default=0, ge=0, le=MAX_DELAY_SECONDS)
    beat_limit: int = Field(default=DEFAULT_BEAT_LIMIT, ge=1, le=MAX_BEAT_LIMIT)


class ImageStyleView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str


class ImageServiceView(BaseModel):
    """The image service as the server sees it: configured, up, and its catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    configured: bool
    reachable: bool = False
    loaded: bool = False
    #: The checkpoint loaded right now (shared by every client).
    checkpoint: str | None = None
    queued: int = 0
    checkpoints: list[str] = Field(default_factory=list)
    styles: list[ImageStyleView] = Field(default_factory=list)
    ratios: list[str] = Field(default_factory=list)
    steps: list[int] = Field(default_factory=list)
    error: str | None = None


class ImagePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=2000)
    ratio: str = "1:1"
    count: int = Field(default=1, ge=1, le=4)
    #: Unsaved image preferences to try; the saved ones when absent.
    images: dict[str, Any] | None = None


class ImagePreviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_url: str
    seed: int | None = None
    width: int
    height: int
    seconds: float | None = None


class ImagePreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    images: list[ImagePreviewItem]


class CharacterPromptView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    name: str
    prefix: str = ""
    suffix: str = ""
    portrait_asset_id: UUID | None = None


class StoryPromptsView(BaseModel):
    """The player's words added to this story's prompts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    llm_prefix: str = ""
    llm_suffix: str = ""
    image_prefix: str = ""
    image_suffix: str = ""
    version: int
    characters: list[CharacterPromptView] = Field(default_factory=list)


class CharacterPromptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    prefix: str = Field(default="", max_length=400)
    suffix: str = Field(default="", max_length=400)


class StoryPromptsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_prefix: str = Field(default="", max_length=2000)
    llm_suffix: str = Field(default="", max_length=2000)
    image_prefix: str = Field(default="", max_length=400)
    image_suffix: str = Field(default="", max_length=400)
    characters: list[CharacterPromptUpdate] = Field(default_factory=list)
    expected_version: int = Field(ge=0)


class MapUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: A PNG, JPEG or WebP picture as a data URL.
    data_url: str = Field(min_length=32, max_length=24_000_000)


class MapPlacesRequest(BaseModel):
    """The world's own place names, to match unlabelled drawings to."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    known: list[str] = Field(default_factory=list, max_length=60)


class TerrainGridView(BaseModel):
    """What covers a map: rows of terrain letters, top row first (cells joined)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cols: int = Field(ge=2, le=48)
    rows: int = Field(ge=2, le=48)
    cells: str = Field(min_length=4, max_length=2304)


class TerrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cols: int = Field(default=24, ge=4, le=48)
    rows: int = Field(default=16, ge=4, le=48)


class TerrainView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    terrain: TerrainGridView | None
    model: str
    seconds: float
    cost_usd: float


class MapPaintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=2000)
    ratio: str = "16:9"


class MapImageView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    width: int
    height: int


class MapPlaceView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(default="", max_length=32)
    point: tuple[int, int]


class MapRoadView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Indexes into the places sent with it.
    a: int = Field(ge=0)
    b: int = Field(ge=0)
    by: str = Field(default="road", max_length=16)
    points: list[tuple[int, int]] = Field(default_factory=list, max_length=16)


class MapPlacesView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    places: list[MapPlaceView]
    model: str
    seconds: float
    cost_usd: float


class MapRoadsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    places: list[MapPlaceView] = Field(min_length=2, max_length=64)


class MapRoadsView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    roads: list[MapRoadView]
    model: str
    seconds: float
    cost_usd: float


class PortraitPaintRequest(BaseModel):
    """Paint a character from words: how they look."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=4000)
    #: Send ``prompt`` to the image service exactly as written (the player
    #: edited the whole prompt); otherwise the house style is added to it.
    raw: bool = False


class PortraitPromptView(BaseModel):
    """What painting would send the image service, before it is sent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: The whole prompt: the words, then the house style's wording.
    prompt: str
    ratio: str
    checkpoint: str | None = None
    style: str | None = None
    mode: str
    #: "random", "stable" or "fixed" (then ``seed`` is the number).
    seed_mode: str
    seed: int | None = None


class WritingField(BaseModel):
    """One studio field: filled ones are context, empty ones get written."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=48)
    label: str = Field(min_length=1, max_length=80)
    hint: str = Field(default="", max_length=300)
    value: str = Field(default="", max_length=4000)
    max_length: int = Field(default=600, ge=20, le=4000)


class WritingPlace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)


class WritingEnhanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["character", "world"]
    overview: str = Field(min_length=1, max_length=6000)
    name: str = Field(default="", max_length=128)


class WritingEnhanceView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    model: str
    seconds: float
    cost_usd: float


class WritingSampleRequest(BaseModel):
    """Hear a character speak: a short exchange in a situation the player picks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(default="", max_length=128)
    #: What the studio knows of their voice (tone, example lines, manner).
    fields: list[WritingField] = Field(default_factory=list, max_length=20)
    situation: str = Field(min_length=3, max_length=300)
    #: Who speaks to them ("A stranger", "An old friend").
    other: str = Field(default="A stranger", min_length=1, max_length=60)


class WritingSampleLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: "them" (the character) or "other".
    who: Literal["them", "other"]
    text: str


class WritingSampleView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    other: str
    lines: list[WritingSampleLine]
    model: str
    seconds: float
    cost_usd: float


class WritingFillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["character", "world"]
    overview: str = Field(default="", max_length=6000)
    name: str = Field(default="", max_length=128)
    fields: list[WritingField] = Field(default_factory=list, max_length=40)
    places: list[WritingPlace] = Field(default_factory=list, max_length=40)
    #: How many new places to add (worlds).
    add_places: int = Field(default=0, ge=0, le=12)
    #: The kinds of place the studio offers; each written place picks one.
    place_kinds: list[str] = Field(default_factory=list, max_length=40)


class WritingFilledPlace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    new: bool
    kind: str = ""


class WritingFillView(BaseModel):
    """Text for the empty fields only (by key), and places described or added."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    values: dict[str, str]
    places: list[WritingFilledPlace]
    model: str
    seconds: float
    cost_usd: float


class FaceView(BaseModel):
    """Where the map reader sees a face: [x, y, w, h] fractions, or none."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    face: list[float] | None = None
    model: str
    seconds: float
    cost_usd: float


class PlaceMapRequest(BaseModel):
    """A place's own map and its spots; no picture takes the map away."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID | None = None
    spots: list[MapPlaceView] = Field(default_factory=list, max_length=32)
    expected_version: int = Field(ge=0)


class WorldMapPlace(MapPlaceView):
    #: The world location this pin is; absent mints a new place.
    key: str | None = Field(default=None, max_length=64)


class WorldMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    places: list[WorldMapPlace] = Field(min_length=1, max_length=64)
    roads: list[MapRoadView] = Field(default_factory=list, max_length=256)
    shortest_phases: int = Field(ge=1, le=999)
    longest_phases: int = Field(ge=1, le=999)
    #: What covers the map; roads through hard country take longer.
    terrain: TerrainGridView | None = None
    expected_version: int = Field(ge=0)
