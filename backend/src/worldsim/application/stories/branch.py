"""Branch a story from one of its turns: a new story, the original untouched.

The branch is the source exactly as it stood at the end of that turn: its
changeable state from the turn's checkpoint, its history (events, scenes,
narration, observations, memories, summaries, finished pictures) up to the
turn. Nothing is written again by a model: a turn whose state was not kept
is refused, never rebuilt. Idempotent like story creation (same key, same
request: the same branch).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from worldsim.application.orchestration.service import derive_run_id
from worldsim.application.orchestration.stage1 import UnitOfWorkFactory
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.branches import BranchCopy, StoryBranchOrigin, branch_title
from worldsim.domain.enums import PhaseRunState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_world_id
from worldsim.domain.stories import StoryCatalogEntry, StoryCreationReceipt
from worldsim.domain.time import utcnow

STILL_WRITING = "This turn is still being written. Try again in a moment."
NOT_KEPT = (
    "This turn was played before turns were kept for branching, so its exact state "
    "isn't stored. Turns played from now on can be branched."
)
NOT_PLAYED = "That turn hasn't been played yet."


@dataclass(frozen=True)
class BranchResult:
    story_id: UUID
    world_id: UUID
    title: str
    role: str
    character_id: UUID | None
    absolute_index: int
    replayed: bool
    #: How ids were renamed (None on a replay); tests read it.
    copy: BranchCopy | None = None


def _request_hash(source_id: UUID, absolute_index: int, title: str | None) -> str:
    canonical = json.dumps(
        {"kind": "branch", "source": str(source_id), "index": absolute_index, "title": title},
        sort_keys=True,
    )
    return "branch:" + hashlib.sha256(canonical.encode()).hexdigest()


async def branch_story(
    uow_factory: UnitOfWorkFactory,
    source_id: UUID,
    absolute_index: int,
    title: str | None,
    operator: str,
    idempotency_key: str,
    *,
    writing: bool = False,
) -> BranchResult:
    """Copy ``source_id`` as it was at the end of turn ``absolute_index``.

    ``writing``: the story still has words or day-end work running behind
    its last turn (this process knows; another process's work shows as
    missing narration or a missing checkpoint).
    """
    key = idempotency_key.strip()
    if not key:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "idempotency key is required")
    clean_title = title.strip() if title and title.strip() else None
    request_hash = _request_hash(source_id, absolute_index, clean_title)
    async with uow_factory() as uow:
        existing = await uow.stories.find_receipt(operator, key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "idempotency key was used for a different request",
                )
            return await _replay(uow, existing.created_world_id)
        source = await uow.stories.get_catalog(source_id)
        await _require_branchable(uow, source_id, absolute_index, writing=writing)
        head = await uow.checkpoints.head(source_id, absolute_index)
        state = await uow.checkpoints.state(source_id, absolute_index)
        assert head is not None and state is not None
        world_id = new_world_id()
        copy = await uow.checkpoints.copy_branch(source_id, absolute_index, head, state, world_id)
        name = (clean_title or branch_title(source.title, absolute_index))[:128]
        now = utcnow()
        cover = source.cover_asset_id
        if cover is not None:
            cover = UUID(copy.remap.get(str(cover), str(cover)))
        await uow.stories.put_catalog(
            StoryCatalogEntry(
                world_id=world_id,
                title=name,
                cover_asset_id=cover,
                created_at=now,
                last_played_at=now,
                archived_at=None,
                metadata_version=1,
            )
        )
        await uow.checkpoints.add_origin(
            StoryBranchOrigin(
                world_id=world_id,
                source_world_id=source_id,
                source_index=absolute_index,
                source_title=source.title,
                created_at=now,
            )
        )
        grant = await uow.roles.get_for_world(world_id)
        try:
            await uow.stories.put_receipt(
                StoryCreationReceipt(
                    operator=operator,
                    idempotency_key=key,
                    request_hash=request_hash,
                    created_world_id=world_id,
                    created_at=now,
                )
            )
            await uow.commit()
        except IntegrityError:
            await uow.rollback()
            async with uow_factory() as fresh:
                raced = await fresh.stories.find_receipt(operator, key)
                if raced is None or raced.request_hash != request_hash:
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "idempotency key was used for a different request",
                    ) from None
                return await _replay(fresh, raced.created_world_id)
    return BranchResult(
        story_id=world_id,
        world_id=world_id,
        title=name,
        role=grant.role.value if grant is not None else "watcher",
        character_id=grant.character_id if grant is not None else None,
        absolute_index=absolute_index,
        replayed=False,
        copy=copy,
    )


async def branchable_turns(uow: UnitOfWork, world_id: UUID) -> list[int]:
    """Turns of this story that can be branched from, oldest first."""
    return [head.absolute_index for head in await uow.checkpoints.heads(world_id)]


async def _require_branchable(
    uow: UnitOfWork, world_id: UUID, absolute_index: int, *, writing: bool
) -> None:
    """Refuse plainly, in the player's words, a turn that can't be branched exactly."""
    if absolute_index < 1:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Choose a turn that has been played.")
    try:
        run = await uow.phases.get_run(derive_run_id(world_id, absolute_index))
    except DomainError:
        run = None
    if run is None or run.state.value != PhaseRunState.COMPLETED.value:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, NOT_PLAYED)
    head = await uow.checkpoints.head(world_id, absolute_index)
    if head is None:
        latest = await uow.phases.latest_run(world_id)
        is_latest = latest is not None and latest.absolute_index == absolute_index
        if is_latest and writing:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, STILL_WRITING)
        raise DomainError(ErrorCode.PRECONDITION_FAILED, NOT_KEPT)
    if await uow.checkpoints.unnarrated_scenes(world_id, absolute_index):
        raise DomainError(ErrorCode.PRECONDITION_FAILED, STILL_WRITING)


async def _replay(uow: UnitOfWork, world_id: UUID) -> BranchResult:
    entry = await uow.stories.get_catalog(world_id)
    grant = await uow.roles.get_for_world(world_id)
    origins = await uow.checkpoints.origins([world_id])
    origin = origins.get(world_id)
    return BranchResult(
        story_id=world_id,
        world_id=world_id,
        title=entry.title,
        role=grant.role.value if grant is not None else "watcher",
        character_id=grant.character_id if grant is not None else None,
        absolute_index=origin.source_index if origin is not None else 0,
        replayed=True,
    )
