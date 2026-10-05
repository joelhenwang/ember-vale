"""Autoplay state persistence (E5 observatory)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class AutoplayRow(Base):
    __tablename__ = "autoplay"

    world_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("world.id", name="fk_autoplay_world"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(16))
    delay_seconds: Mapped[int] = mapped_column(Integer)
    beats_left: Mapped[int] = mapped_column(Integer)
    beats_run: Mapped[int] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stop_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("status IN ('playing', 'paused')", name="ck_autoplay_status"),
        CheckConstraint("delay_seconds >= 0", name="ck_autoplay_delay"),
        CheckConstraint("beats_left >= 0", name="ck_autoplay_beats_left"),
        CheckConstraint("beats_run >= 0", name="ck_autoplay_beats_run"),
        CheckConstraint("version >= 0", name="ck_autoplay_version"),
    )
