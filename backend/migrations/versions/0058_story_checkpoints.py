"""Every turn keeps a checkpoint, so a story can branch from any turn played since.

Most story state is updated in place (where people stand, stamina, items,
rumours, relationships, intentions), so the state at an earlier turn cannot
be rebuilt from what was stored before (docs/evidence/story-branches-001).
``story_checkpoint`` keeps that mutable state as one JSON document per turn,
written at the turn's end with the event cursor it pairs with.
``story_branch`` records where a branched story came from. Both are tables
of their own, so story creation keeps working against older schemas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0058_story_checkpoints"
down_revision = "0057_image_job_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_checkpoint",
        sa.Column(
            "world_id",
            UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_checkpoint_world"),
            primary_key=True,
        ),
        sa.Column("absolute_index", sa.Integer(), primary_key=True),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("state", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("absolute_index >= 0", name="ck_checkpoint_index"),
    )
    op.create_table(
        "story_branch",
        sa.Column(
            "world_id",
            UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_branch_world"),
            primary_key=True,
        ),
        sa.Column(
            "source_world_id",
            UUID(as_uuid=True),
            sa.ForeignKey("world.id", name="fk_branch_source"),
            nullable=False,
            index=True,
        ),
        sa.Column("source_index", sa.Integer(), nullable=False),
        sa.Column("source_title", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("story_branch")
    op.drop_table("story_checkpoint")
