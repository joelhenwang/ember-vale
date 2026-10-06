"""Director trigger, proposal, and validation contracts (owned by S2-DIRECTOR-001).

The Director proposes opportunities, never outcomes. A deterministic
trigger decides whether the model runs at all; a deterministic
validator decides whether its proposal lands. Requested powers
beyond the supported set are rejected, and permanent change (harm,
death, rules) is not expressible. A hook may bring one new character
into the world (``spawn_npc`` with an ``npc`` description), within a
per-story limit, so openings can name someone characters can meet.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import (
    ArcId,
    CharacterId,
    HookId,
    ItemInstanceId,
    LocationId,
    WorldId,
)
from worldsim.domain.narrative import NarrativeArc, NarrativeHook

#: Phases between Director runs unless overridden in world config.
DIRECTOR_COOLDOWN_PHASES = 3
#: Caps enforced when accepting proposals.
MAX_ACTIVE_HOOKS = 3
MAX_ACTIVE_ARCS = 2
#: Powers a proposal may request. Anything else is rejected.
SUPPORTED_POWERS = frozenset({"spawn_npc", "new_location", "place_item"})


#: New characters the director may add to one story.
MAX_SPAWNED_NPCS = 3
SPAWNED_CONFIG_KEY = "director.spawned_npcs"
#: New places the director may add to one story.
MAX_ADDED_PLACES = 3
ADDED_PLACES_CONFIG_KEY = "director.added_places"


class PlaceSpec(BaseModel):
    """A new place an opening needs, reached from an existing one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=600)
    connect_to: LocationId
    travel_phases: int = Field(default=1, ge=1, le=4)


class AddedPlace(PlaceSpec):
    """An accepted new place, with the id it will be created under."""

    id: LocationId


class NpcSpec(BaseModel):
    """A new character an opening needs: who, what they are like, where."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=600)
    pronouns: str = Field(default="", max_length=40)
    #: Left out: the place this same proposal adds.
    location_id: LocationId | None = None


class ItemSpec(BaseModel):
    """A one-off thing an opening leaves somewhere (a lost ledger, a locket)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=600)
    #: Left out: the place this same proposal adds.
    location_id: LocationId | None = None


class PlacedItem(BaseModel):
    """An accepted item, with its id and the concrete place it lies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: ItemInstanceId
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=600)
    location_id: LocationId


class SpawnedNpc(BaseModel):
    """An accepted new character, with its id and the concrete place it starts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: CharacterId
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=600)
    pronouns: str = Field(default="", max_length=40)
    location_id: LocationId


class HookEnding(BaseModel):
    """A running hook the recent happenings have settled, and how it ended."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hook_id: HookId
    ending: str = Field(min_length=1, max_length=240)


class DirectorProposal(BaseModel):
    """One model-proposed opportunity (or an explicit no-op)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str = Field(pattern="^(propose_hook|propose_arc|noop)$")
    title: str = Field(default="", max_length=128)
    purpose: str = Field(default="", max_length=1024)
    requested_powers: list[str] = Field(default_factory=list)
    participant_ids: list[CharacterId] = Field(default_factory=list)
    reason: str = Field(default="", max_length=512)
    npc: NpcSpec | None = None
    item: ItemSpec | None = None
    place: PlaceSpec | None = None
    #: Running hooks to close, with their endings (allowed with any action).
    resolved: list[HookEnding] = Field(default_factory=list)


class DirectorDecision(BaseModel):
    """Validated outcome: accepted rows or a rejection reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    hook: NarrativeHook | None = None
    arc: NarrativeArc | None = None
    npc: SpawnedNpc | None = None
    item: PlacedItem | None = None
    place: AddedPlace | None = None
    reason: str = Field(default="", max_length=512)
    #: Hooks closed by this decision, applied even when nothing new is accepted.
    closed: list[HookEnding] = Field(default_factory=list)


def should_trigger(
    absolute: int, last_absolute: int | None, cooldown: int = DIRECTOR_COOLDOWN_PHASES
) -> bool:
    """Run when the cooldown elapsed since the last attempt (never seen counts)."""
    if last_absolute is None:
        return True
    return absolute - last_absolute >= max(1, cooldown)


def validate_proposal(
    proposal: DirectorProposal,
    world_id: WorldId,
    known_character_ids: frozenset[CharacterId],
    active_hooks: int,
    active_arcs: int,
    hook_id: HookId,
    arc_id: ArcId,
    *,
    known_location_ids: frozenset[LocationId] = frozenset(),
    spawns_left: int = 0,
    npc_id: CharacterId | None = None,
    item_id: ItemInstanceId | None = None,
    place_id: LocationId | None = None,
    places_left: int = 0,
    known_place_names: frozenset[str] = frozenset(),
    open_hook_ids: frozenset[HookId] = frozenset(),
) -> DirectorDecision:
    """Accept well-formed proposals inside privilege and budget; else reject.

    Endings for running hooks are kept whatever happens to the new
    proposal, and they free their slots for it.
    """
    closed = _endings(proposal, open_hook_ids)
    decision = _validate(
        proposal,
        world_id,
        known_character_ids,
        active_hooks - len(closed),
        active_arcs,
        hook_id,
        arc_id,
        known_location_ids=known_location_ids,
        spawns_left=spawns_left,
        npc_id=npc_id,
        item_id=item_id,
        place_id=place_id,
        places_left=places_left,
        known_place_names=known_place_names,
    )
    return decision.model_copy(update={"closed": closed}) if closed else decision


def _endings(proposal: DirectorProposal, open_hook_ids: frozenset[HookId]) -> list[HookEnding]:
    seen: set[HookId] = set()
    kept: list[HookEnding] = []
    for ending in proposal.resolved:
        if ending.hook_id in open_hook_ids and ending.hook_id not in seen:
            seen.add(ending.hook_id)
            kept.append(ending)
    return kept


def _validate(
    proposal: DirectorProposal,
    world_id: WorldId,
    known_character_ids: frozenset[CharacterId],
    active_hooks: int,
    active_arcs: int,
    hook_id: HookId,
    arc_id: ArcId,
    *,
    known_location_ids: frozenset[LocationId],
    spawns_left: int,
    npc_id: CharacterId | None,
    item_id: ItemInstanceId | None,
    place_id: LocationId | None,
    places_left: int,
    known_place_names: frozenset[str],
) -> DirectorDecision:
    if proposal.action == "noop":
        return DirectorDecision(accepted=False, reason=proposal.reason or "no-op")
    if not proposal.title.strip():
        return DirectorDecision(accepted=False, reason="proposals need a title")
    unknown = [p for p in proposal.requested_powers if p not in SUPPORTED_POWERS]
    if unknown:
        return DirectorDecision(
            accepted=False, reason=f"unsupported powers: {','.join(sorted(unknown))}"
        )
    strangers = [c for c in proposal.participant_ids if c not in known_character_ids]
    if strangers:
        return DirectorDecision(accepted=False, reason="participants must be known characters")
    if proposal.action == "propose_hook":
        if active_hooks >= MAX_ACTIVE_HOOKS:
            return DirectorDecision(accepted=False, reason="hook budget exhausted")
        added: AddedPlace | None = None
        if proposal.place is not None or "new_location" in proposal.requested_powers:
            place = proposal.place
            if place is None or place_id is None:
                return DirectorDecision(
                    accepted=False, reason="new_location needs a place: name, connect_to"
                )
            if places_left <= 0:
                return DirectorDecision(accepted=False, reason="no new places left for this story")
            if place.connect_to not in known_location_ids:
                return DirectorDecision(
                    accepted=False,
                    reason=f"new place must connect to a known location: {place.connect_to}",
                )
            if place.name.strip().casefold() in known_place_names:
                return DirectorDecision(
                    accepted=False, reason=f"a place named {place.name!r} already exists"
                )
            added = AddedPlace(**place.model_dump(), id=place_id)
            # The new place can host the opening's new character or item.
            known_location_ids = known_location_ids | {place_id}
        default_place = added.id if added is not None else None
        spawned: SpawnedNpc | None = None
        if proposal.npc is not None or "spawn_npc" in proposal.requested_powers:
            npc = proposal.npc
            if npc is not None and npc.location_id is None:
                npc = npc.model_copy(update={"location_id": default_place})
            denial = _spawn_denial(npc, known_location_ids, spawns_left, npc_id)
            if denial is not None:
                return DirectorDecision(accepted=False, reason=denial)
            assert npc is not None and npc_id is not None and npc.location_id is not None
            spawned = SpawnedNpc(**npc.model_dump(), id=npc_id)
        placed: PlacedItem | None = None
        if proposal.item is not None or "place_item" in proposal.requested_powers:
            item = proposal.item
            if item is not None and item.location_id is None:
                item = item.model_copy(update={"location_id": default_place})
            if item is None or item_id is None:
                return DirectorDecision(
                    accepted=False, reason="place_item needs an item: name, location_id"
                )
            if item.location_id is None or item.location_id not in known_location_ids:
                return DirectorDecision(
                    accepted=False,
                    reason=f"item place is not a known location: {item.location_id}",
                )
            placed = PlacedItem(**item.model_dump(), id=item_id)
        participants = list(proposal.participant_ids)
        powers = list(proposal.requested_powers)
        if placed is not None and "place_item" not in powers:
            powers.append("place_item")
        if added is not None and "new_location" not in powers:
            powers.append("new_location")
        if spawned is not None:
            # A hook naming nobody is heard by everyone; naming only the new
            # character would hide it from the cast it is meant to reach.
            if participants:
                participants.append(spawned.id)
            if "spawn_npc" not in powers:
                powers.append("spawn_npc")
        return DirectorDecision(
            accepted=True,
            hook=NarrativeHook(
                id=hook_id,
                world_id=world_id,
                title=proposal.title.strip(),
                purpose=proposal.purpose,
                requested_powers=powers,
                participant_ids=participants,
            ),
            npc=spawned,
            item=placed,
            place=added,
        )
    if active_arcs >= MAX_ACTIVE_ARCS:
        return DirectorDecision(accepted=False, reason="arc budget exhausted")
    return DirectorDecision(
        accepted=True,
        arc=NarrativeArc(
            id=arc_id,
            world_id=world_id,
            title=proposal.title.strip(),
            purpose=proposal.purpose,
        ),
    )


def _spawn_denial(
    npc: NpcSpec | None,
    known_location_ids: frozenset[LocationId],
    spawns_left: int,
    npc_id: CharacterId | None,
) -> str | None:
    if npc is None:
        return "spawn_npc needs an npc: name, description, location_id"
    if npc_id is None or spawns_left <= 0:
        return "no new characters left for this story"
    if npc.location_id is None or npc.location_id not in known_location_ids:
        return f"npc place is not a known location: {npc.location_id}"
    return None
