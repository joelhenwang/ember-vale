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


class NpcSpec(BaseModel):
    """A new character an opening needs: who, what they are like, where."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=600)
    location_id: LocationId


class ItemSpec(BaseModel):
    """A one-off thing an opening leaves somewhere (a lost ledger, a locket)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=600)
    location_id: LocationId


class PlacedItem(ItemSpec):
    """An accepted item, with the id it will be created under."""

    id: ItemInstanceId


class SpawnedNpc(NpcSpec):
    """An accepted new character, with the id it will be created under."""

    id: CharacterId


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


class DirectorDecision(BaseModel):
    """Validated outcome: accepted rows or a rejection reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    hook: NarrativeHook | None = None
    arc: NarrativeArc | None = None
    npc: SpawnedNpc | None = None
    item: PlacedItem | None = None
    reason: str = Field(default="", max_length=512)


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
) -> DirectorDecision:
    """Accept well-formed proposals inside privilege and budget; else reject."""
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
        spawned: SpawnedNpc | None = None
        if proposal.npc is not None or "spawn_npc" in proposal.requested_powers:
            denial = _spawn_denial(proposal.npc, known_location_ids, spawns_left, npc_id)
            if denial is not None:
                return DirectorDecision(accepted=False, reason=denial)
            assert proposal.npc is not None and npc_id is not None
            spawned = SpawnedNpc(**proposal.npc.model_dump(), id=npc_id)
        placed: PlacedItem | None = None
        if proposal.item is not None or "place_item" in proposal.requested_powers:
            if proposal.item is None or item_id is None:
                return DirectorDecision(
                    accepted=False, reason="place_item needs an item: name, location_id"
                )
            if proposal.item.location_id not in known_location_ids:
                return DirectorDecision(
                    accepted=False,
                    reason=f"item place is not a known location: {proposal.item.location_id}",
                )
            placed = PlacedItem(**proposal.item.model_dump(), id=item_id)
        participants = list(proposal.participant_ids)
        powers = list(proposal.requested_powers)
        if placed is not None and "place_item" not in powers:
            powers.append("place_item")
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
    if npc.location_id not in known_location_ids:
        return f"npc place is not a known location: {npc.location_id}"
    return None
