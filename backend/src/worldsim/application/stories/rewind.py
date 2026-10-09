"""Go back to a kept turn of the same story (rewind-001).

The story's changeable state comes back from the turn's checkpoint and every
turn after it is removed, so the story plays on from that turn as if the
later turns never happened. Nothing is lost: in the same transaction, before
anything is removed, the story as it stands is saved as a branch from its
newest turn ("the path not taken"). If that save fails, nothing changes.
Idempotent like branching (same key, same request: the same answer).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from worldsim.application.execution import SlotBusy, admit, new_owner, phase_scope
from worldsim.application.orchestration.stage1 import UnitOfWorkFactory
from worldsim.application.stories.branch import (
    NOT_KEPT,
    STILL_WRITING,
    _require_branchable,  # pyright: ignore[reportPrivateUsage]
    copy_into_new_story,
)
from worldsim.application.tasks.service import TaskService
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.autoplay import AutoplayStatus, StopReason, pause
from worldsim.domain.branches import BranchCopy, path_not_taken_title
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.stories import StoryCreationReceipt
from worldsim.domain.time import utcnow

ALREADY_LATEST = "This is already the newest turn of the story."
PLAYING = "A turn is being played right now. Try again when it has finished."
REWIND_NOT_KEPT = "This turn's exact state isn't kept, so the story can't go back to it."
NEWEST_NOT_KEPT = (
    "The newest turn wasn't kept, so the turns after this one couldn't be saved as a "
    "story of their own. Play one more turn, then try again."
)
REWOUND_DETAIL = "Went back to an earlier turn."


@dataclass(frozen=True)
class RewindResult:
    story_id: UUID
    absolute_index: int
    #: The story that keeps the removed turns ("the path not taken").
    saved_story_id: UUID
    saved_title: str
    #: The seat (player, watcher...), the same in both stories.
    role: str
    #: Turns removed from this story.
    removed_turns: int
    replayed: bool
    #: Rows removed or restored, per table (empty on a replay); tests read it.
    counts: dict[str, int]
    #: How the saved story's ids were renamed (None on a replay); tests read it.
    copy: BranchCopy | None = None


def _request_hash(world_id: UUID, absolute_index: int) -> str:
    canonical = json.dumps(
        {"kind": "rewind", "story": str(world_id), "index": absolute_index}, sort_keys=True
    )
    return "rewind:" + hashlib.sha256(canonical.encode()).hexdigest()


async def rewind_story(
    uow_factory: UnitOfWorkFactory,
    world_id: UUID,
    absolute_index: int,
    operator: str,
    idempotency_key: str,
    *,
    writing: bool = False,
) -> RewindResult:
    """Put ``world_id`` back at the end of turn ``absolute_index``.

    ``writing``: this process still has words or day-end work running for
    the story. The next turn's execution slot is held while it runs, so no
    turn can start meanwhile.
    """
    key = idempotency_key.strip()
    if not key:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "idempotency key is required")
    request_hash = _request_hash(world_id, absolute_index)
    async with uow_factory() as uow:
        replay = await _find_replay(uow, operator, key, request_hash, world_id, absolute_index)
        if replay is not None:
            return replay
        await uow.stories.get_catalog(world_id)  # NOT_FOUND for unknown stories
        latest = await uow.checkpoints.latest_completed(world_id)
    if latest is not None and absolute_index == latest:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, ALREADY_LATEST)
    if latest is not None and absolute_index < latest and writing:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, STILL_WRITING)
    owner = new_owner("rewind")
    try:
        slot = await admit(uow_factory, world_id, phase_scope((latest or 0) + 1), owner)
    except SlotBusy:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, PLAYING) from None
    try:
        return await _rewind(
            uow_factory, world_id, absolute_index, latest, operator, key, request_hash
        )
    finally:
        # Back to pending, never left running: the next turn claims it as usual.
        await TaskService(uow_factory).reset_slot(slot.id, owner)


async def _rewind(
    uow_factory: UnitOfWorkFactory,
    world_id: UUID,
    absolute_index: int,
    latest: int | None,
    operator: str,
    key: str,
    request_hash: str,
) -> RewindResult:
    async with uow_factory() as uow:
        replay = await _find_replay(uow, operator, key, request_hash, world_id, absolute_index)
        if replay is not None:
            return replay
        if await uow.checkpoints.latest_completed(world_id) != latest:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, PLAYING)
        try:
            await _require_branchable(uow, world_id, absolute_index, writing=False)
        except DomainError as error:
            if str(error) == NOT_KEPT:
                raise DomainError(ErrorCode.PRECONDITION_FAILED, REWIND_NOT_KEPT) from None
            raise
        assert latest is not None  # the turn was played, so a newest turn exists
        if await uow.checkpoints.head(world_id, latest) is None:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, NEWEST_NOT_KEPT)
        if await uow.checkpoints.unnarrated_scenes(world_id, latest):
            raise DomainError(ErrorCode.PRECONDITION_FAILED, STILL_WRITING)

        # 1. Save the path not taken; anything failing here stops the rewind.
        saved_id, saved_title, copy = await copy_into_new_story(
            uow, world_id, latest, None, path_not_taken_title
        )
        # 2. Go back.
        head = await uow.checkpoints.head(world_id, absolute_index)
        state = await uow.checkpoints.state(world_id, absolute_index)
        assert head is not None and state is not None
        counts = await uow.checkpoints.rewind(world_id, absolute_index, head, state)
        playing = await uow.autoplay.get(world_id, for_update=True)
        if playing.status == AutoplayStatus.PLAYING:
            await uow.autoplay.save(pause(playing, StopReason.USER, REWOUND_DETAIL))
        try:
            await uow.stories.put_receipt(
                StoryCreationReceipt(
                    operator=operator,
                    idempotency_key=key,
                    request_hash=request_hash,
                    created_world_id=saved_id,
                    created_at=utcnow(),
                )
            )
            await uow.commit()
        except IntegrityError:
            await uow.rollback()
            async with uow_factory() as fresh:
                raced = await _find_replay(
                    fresh, operator, key, request_hash, world_id, absolute_index
                )
                if raced is None:
                    raise
                return raced
    return RewindResult(
        story_id=world_id,
        absolute_index=absolute_index,
        saved_story_id=saved_id,
        saved_title=saved_title,
        role=await _role(uow_factory, world_id),
        removed_turns=latest - absolute_index,
        replayed=False,
        counts=counts,
        copy=copy,
    )


async def _find_replay(
    uow: UnitOfWork,
    operator: str,
    key: str,
    request_hash: str,
    world_id: UUID,
    absolute_index: int,
) -> RewindResult | None:
    existing = await uow.stories.find_receipt(operator, key)
    if existing is None:
        return None
    if existing.request_hash != request_hash:
        raise DomainError(
            ErrorCode.IDEMPOTENCY_CONFLICT, "idempotency key was used for a different request"
        )
    saved = await uow.stories.get_catalog(existing.created_world_id)
    origin = (await uow.checkpoints.origins([saved.world_id])).get(saved.world_id)
    removed = origin.source_index - absolute_index if origin is not None else 0
    return RewindResult(
        story_id=world_id,
        absolute_index=absolute_index,
        saved_story_id=saved.world_id,
        saved_title=saved.title,
        role=await _role_in(uow, world_id),
        removed_turns=removed,
        replayed=True,
        counts={},
    )


async def _role_in(uow: UnitOfWork, world_id: UUID) -> str:
    grant = await uow.roles.get_for_world(world_id)
    return grant.role.value if grant is not None else "watcher"


async def _role(uow_factory: UnitOfWorkFactory, world_id: UUID) -> str:
    async with uow_factory() as uow:
        return await _role_in(uow, world_id)
