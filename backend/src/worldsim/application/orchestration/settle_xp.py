"""A settled rumour gives a combat story's party experience (quest-xp-001).

Runs after the rumour is closed (the director's ending, or the scene
commit that carried the resolver's ``hook_settled``), in its own
transaction, and never fails the turn. One event per rumour
(``derive_settle_xp_event_id``) holds the rows the story log shows, so a
replayed settle finds it and gives nothing twice.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import EventType, NarrativeStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import derive_settle_xp_event_id
from worldsim.domain.party import chooser_keys, party_took_part
from worldsim.domain.rules.dnd.data import DataTables
from worldsim.domain.rules.dnd.quests import award_settled
from worldsim.domain.time import split_absolute

logger = logging.getLogger(__name__)


async def award_settled_hooks(
    factory: Callable[[], UnitOfWork],
    tables: Callable[[], DataTables],
    world_id: UUID,
    hook_ids: Iterable[UUID],
    *,
    absolute_index: int,
    run_id: UUID | None,
    scene_event_id: UUID | None = None,
    xp_scale: int = 1,
) -> list[UUID]:
    """Award each closed rumour's experience once; the events written."""
    written: list[UUID] = []
    for hook_id in dict.fromkeys(hook_ids):
        try:
            if await _award_one(
                factory,
                tables,
                world_id,
                hook_id,
                absolute_index,
                run_id,
                scene_event_id,
                xp_scale,
            ):
                written.append(derive_settle_xp_event_id(hook_id))
        except DomainError:
            logger.warning("settle xp for hook %s not given", hook_id, exc_info=True)
    return written


async def _award_one(
    factory: Callable[[], UnitOfWork],
    tables: Callable[[], DataTables],
    world_id: UUID,
    hook_id: UUID,
    absolute_index: int,
    run_id: UUID | None,
    scene_event_id: UUID | None,
    xp_scale: int = 1,
) -> bool:
    event_id = derive_settle_xp_event_id(hook_id)
    for _ in range(2):
        async with factory() as uow:
            roster = await uow.party.list_for_world(world_id)
            if not roster:
                return False
            hook = await uow.narrative.get_hook(hook_id)
            if hook.world_id != world_id or hook.status != NarrativeStatus.CLOSED:
                return False
            # Only a rumour the party took part in pays: one whose people include
            # a party member, or that settled in a scene a party member was in.
            # Rumours settle often among others (0-2 in a 6-turn scorecard
            # story), and 50 XP each was a free level every few story days.
            seen = set(hook.participant_ids)
            if scene_event_id is not None:
                try:
                    seen |= set((await uow.events.get_event(scene_event_id)).participant_ids)
                except DomainError as exc:
                    if exc.code is not ErrorCode.NOT_FOUND:
                        raise
            if not party_took_part(roster, seen):
                return False
            try:
                await uow.events.get_event(event_id)
                return False  # already given
            except DomainError as exc:
                if exc.code is not ErrorCode.NOT_FOUND:
                    raise
            award = award_settled(
                tables(),
                hook.title,
                [(member.name_key, member.sheet) for member in roster],
                chooses=chooser_keys(
                    roster, getattr(await uow.roles.get_for_world(world_id), "character_id", None)
                ),
                day=split_absolute(absolute_index)[0],
                xp_scale=xp_scale,
            )
            try:
                for member in roster:
                    await uow.party.save_sheet(
                        member.id, award.sheets[member.name_key], member.version
                    )
                sequence = await uow.events.max_sequence(world_id) + 1
                summary = {
                    "settled": str(hook_id),
                    "rolls": json.dumps(award.rolls, separators=(",", ":")),
                }
                if scene_event_id is not None:
                    summary["scene_event_id"] = str(scene_event_id)
                await uow.events.append_event(
                    WorldEvent(
                        id=event_id,
                        world_id=world_id,
                        sequence=sequence,
                        event_type=EventType.ACTION_RESOLVED,
                        absolute_index=absolute_index,
                        phase_run_id=run_id,
                        participant_ids=sorted(
                            (m.character_id for m in roster if m.character_id is not None),
                            key=str,
                        ),
                        summary=summary,
                        random_result=" | ".join(str(r["text"]) for r in award.rolls)[:512],
                    )
                )
                await uow.commit()
                return True
            except DomainError as exc:
                if exc.code is not ErrorCode.VERSION_CONFLICT:
                    raise
    return False
