"""Scene pictures (table ``scene_picture``, migration 0052)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.jsonvalues import json_list
from worldsim.domain.pictures import PictureMoment, ScenePicture

_COLUMNS = (
    "id, world_id, scene_id, job_id, moment, caption, prompt, character_ids, "
    "location_id, created_phase_index"
)


def _picture(row: Sequence[Any]) -> ScenePicture:
    raw: object = row[7]
    if isinstance(raw, str):  # jsonb arrives as text through plain SQL
        raw = json.loads(raw)
    ids = json_list(raw)
    return ScenePicture(
        id=row[0],
        world_id=row[1],
        scene_id=row[2],
        job_id=row[3],
        moment=PictureMoment(row[4]),
        caption=row[5],
        prompt=row[6],
        character_ids=[UUID(str(i)) for i in ids or []],
        location_id=row[8],
        created_phase_index=row[9],
    )


class SqlAlchemyPictureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, picture: ScenePicture) -> None:
        await self._session.execute(
            text(
                f"INSERT INTO scene_picture ({_COLUMNS}) VALUES (:id, :world_id, :scene_id, "
                ":job_id, :moment, :caption, :prompt, CAST(:character_ids AS jsonb), "
                ":location_id, :created_phase_index)"
            ),
            {
                **picture.model_dump(exclude={"character_ids", "moment"}),
                "moment": picture.moment.value,
                "character_ids": json.dumps([str(i) for i in picture.character_ids]),
            },
        )

    async def get(self, picture_id: UUID) -> ScenePicture:
        row = (
            await self._session.execute(
                text(f"SELECT {_COLUMNS} FROM scene_picture WHERE id = :id"), {"id": picture_id}
            )
        ).first()
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"scene picture {picture_id} not found")
        return _picture(row)

    async def list_for_world(self, world_id: UUID) -> list[ScenePicture]:
        rows = await self._session.execute(
            text(
                f"SELECT {_COLUMNS} FROM scene_picture WHERE world_id = :w "
                "ORDER BY created_phase_index, created_at"
            ),
            {"w": world_id},
        )
        return [_picture(row) for row in rows]

    async def latest_moment_index(self, world_id: UUID) -> int | None:
        """The beat of the newest automatic picture, for the cooldown."""
        return (
            await self._session.execute(
                text(
                    "SELECT max(created_phase_index) FROM scene_picture "
                    "WHERE world_id = :w AND moment <> 'manual'"
                ),
                {"w": world_id},
            )
        ).scalar()
