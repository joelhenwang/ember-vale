"""Server-authoritative autoplay state, one row per story.

The runner admits beats only for rows that are playing, due, and still
watched (``last_seen_at`` within the presence grace period).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0041_autoplay"
down_revision = "0040_observation_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autoplay",
        sa.Column("world_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("delay_seconds", sa.Integer(), nullable=False),
        sa.Column("beats_left", sa.Integer(), nullable=False),
        sa.Column("beats_run", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sa.String(32), nullable=True),
        sa.Column("stop_detail", sa.String(500), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["world_id"], ["world.id"], name="fk_autoplay_world"),
        sa.PrimaryKeyConstraint("world_id", name="pk_autoplay"),
        sa.CheckConstraint("status IN ('playing', 'paused')", name="ck_autoplay_status"),
        sa.CheckConstraint("delay_seconds >= 0", name="ck_autoplay_delay"),
        sa.CheckConstraint("beats_left >= 0", name="ck_autoplay_beats_left"),
        sa.CheckConstraint("beats_run >= 0", name="ck_autoplay_beats_run"),
        sa.CheckConstraint("version >= 0", name="ck_autoplay_version"),
    )
    op.create_index("ix_autoplay_next_due_at", "autoplay", ["next_due_at"])


def downgrade() -> None:
    op.drop_index("ix_autoplay_next_due_at", table_name="autoplay")
    op.drop_table("autoplay")
