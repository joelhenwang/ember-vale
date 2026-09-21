"""Per-step effect identity for directed activities and conditions.

Travel recovery and condition recovery previously matched on status or
display text (active activities, active labels), so an inactive effect
could not prove a step already ran and two steps sharing a label were
conflated. Each directed effect now carries its owning queue step key
in a dedicated nullable column guarded by a partial unique index, so a
replayed or overlapping applier collides on the step identity and
adopts the recorded effect instead of duplicating it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_step_effect_identity"
down_revision = "0033_preset_travel_rev2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity",
        sa.Column("direct_step_key", sa.String(length=128), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE activity SET direct_step_key = payload->>'direct_step_key' "
            "WHERE payload->>'direct_step_key' IS NOT NULL"
        )
    )
    op.create_index(
        "uq_activity_direct_step_key",
        "activity",
        ["direct_step_key"],
        unique=True,
        postgresql_where=sa.text("direct_step_key IS NOT NULL"),
    )
    op.add_column(
        "world_condition",
        sa.Column("source_step_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "uq_condition_source_step_key",
        "world_condition",
        ["source_step_key"],
        unique=True,
        postgresql_where=sa.text("source_step_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_condition_source_step_key", table_name="world_condition")
    op.drop_column("world_condition", "source_step_key")
    op.drop_index("uq_activity_direct_step_key", table_name="activity")
    op.drop_column("activity", "direct_step_key")
