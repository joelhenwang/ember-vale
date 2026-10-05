"""Character intention: the latest stated plan, one row per character.

Decisions and reactions may state an intention; the newest replaces the
old so the next decision reads the current plan.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0042_character_intention"
down_revision = "0041_autoplay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "character_intention",
        sa.Column("character_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("world_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.String(200), nullable=False),
        sa.Column("set_phase_index", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["character.id"], name="fk_intention_character"),
        sa.ForeignKeyConstraint(["world_id"], ["world.id"], name="fk_intention_world"),
        sa.PrimaryKeyConstraint("character_id", name="pk_character_intention"),
        sa.CheckConstraint("set_phase_index >= 0", name="ck_intention_phase"),
    )
    op.create_index("ix_character_intention_world_id", "character_intention", ["world_id"])


def downgrade() -> None:
    op.drop_index("ix_character_intention_world_id", table_name="character_intention")
    op.drop_table("character_intention")
