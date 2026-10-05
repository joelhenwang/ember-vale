"""Character intention persistence (one row per character)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class CharacterIntentionRow(Base):
    __tablename__ = "character_intention"

    character_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("character.id", name="fk_intention_character"),
        primary_key=True,
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_intention_world"), index=True
    )
    text: Mapped[str] = mapped_column(String(200))
    set_phase_index: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("set_phase_index >= 0", name="ck_intention_phase"),)
