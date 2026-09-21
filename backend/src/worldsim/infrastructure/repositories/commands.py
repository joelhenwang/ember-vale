"""Idempotent command record adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.infrastructure.models.commands import UserCommandRow
from worldsim.infrastructure.repositories._common import missing


class SqlAlchemyCommandRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, world_id: UUID, key: str) -> UUID | None:
        row = (
            await self._session.execute(
                select(UserCommandRow).where(
                    UserCommandRow.world_id == world_id,
                    UserCommandRow.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        return row.id if row is not None else None

    async def get_input_hash(self, command_id: UUID) -> str:
        row = await self._session.get(UserCommandRow, command_id)
        if row is None:
            raise missing("command", command_id)
        return row.input_hash

    async def get_result(self, command_id: UUID) -> UUID | None:
        row = await self._session.get(UserCommandRow, command_id)
        if row is None:
            raise missing("command", command_id)
        return row.result_event_id

    async def add(
        self,
        command_id: UUID,
        world_id: UUID,
        key: str,
        actor_role: str,
        command_type: str,
        expected_versions: dict[str, int],
        payload: dict[str, object],
        input_hash: str,
    ) -> None:
        try:
            self._session.add(
                UserCommandRow(
                    id=command_id,
                    world_id=world_id,
                    idempotency_key=key,
                    actor_role=actor_role,
                    command_type=command_type,
                    expected_versions=dict(expected_versions),
                    payload=dict(payload),
                    input_hash=input_hash,
                )
            )
            await self._session.flush()
        except SqlIntegrityError as exc:
            if _constraint_name(exc) == "uq_command_world_key":
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    f"duplicate command key: {key}",
                ) from exc
            raise

    async def set_result(self, command_id: UUID, event_id: UUID) -> None:
        row = await self._session.get(UserCommandRow, command_id)
        if row is None:
            raise missing("command", command_id)
        row.result_event_id = event_id
        await self._session.flush()


def _constraint_name(exc: BaseException) -> str:
    """Name of the violated unique constraint across drivers.

    psycopg surfaces it via ``orig.diag``; asyncpg (the runtime engine
    driver) exposes ``constraint_name`` directly on the driver error, one
    extra nesting level down: SQLAlchemy wraps the raw asyncpg error in
    its own adapter error first. Without the walk, duplicate command
    keys surface as raw IntegrityError and the execution gate cannot
    report "taken".
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        direct = getattr(current, "constraint_name", None)
        if isinstance(direct, str) and direct:
            return direct
        diag = getattr(current, "diag", None)
        name = getattr(diag, "constraint_name", None)
        if isinstance(name, str) and name:
            return name
        for attr in ("orig", "__cause__", "__context__"):
            nxt = getattr(current, attr, None)
            if isinstance(nxt, BaseException) and id(nxt) not in seen:
                break
        current = nxt if isinstance(nxt, BaseException) else None
    return ""
