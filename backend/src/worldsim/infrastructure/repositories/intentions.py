"""Character intention adapter."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.intentions import CharacterIntention
from worldsim.infrastructure.models.intentions import CharacterIntentionRow


class SqlAlchemyIntentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, character_id: UUID) -> CharacterIntention | None:
        row = await self._session.get(CharacterIntentionRow, character_id)
        if row is None:
            return None
        return CharacterIntention(
            character_id=row.character_id,
            world_id=row.world_id,
            text=row.text,
            set_phase_index=row.set_phase_index,
            updated_at=row.updated_at,
        )

    async def list_for_world(self, world_id: UUID) -> dict[UUID, CharacterIntention]:
        """Every character's intention in the world, by character (one query
        where a loop of gets took one a character, perf-turn-001)."""
        rows = (
            await self._session.execute(
                select(CharacterIntentionRow).where(CharacterIntentionRow.world_id == world_id)
            )
        ).scalars()
        return {
            row.character_id: CharacterIntention(
                character_id=row.character_id,
                world_id=row.world_id,
                text=row.text,
                set_phase_index=row.set_phase_index,
                updated_at=row.updated_at,
            )
            for row in rows
        }

    async def set(self, intention: CharacterIntention) -> None:
        """Replace the character's intention (the newest statement wins)."""
        row = await self._session.get(CharacterIntentionRow, intention.character_id)
        if row is None:
            row = CharacterIntentionRow(character_id=intention.character_id)
            self._session.add(row)
        row.world_id = intention.world_id
        row.text = intention.text
        row.set_phase_index = intention.set_phase_index
        row.updated_at = intention.updated_at
        await self._session.flush()
