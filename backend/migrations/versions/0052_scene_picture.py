"""Scene pictures: what to paint for a scene, and its caption in the story.

A table of its own (not columns on image_job) so story creation, which
writes image jobs, keeps working against older schemas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0052_scene_picture"
down_revision = "0051_image_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_picture",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_id", UUID(as_uuid=True), nullable=False),
        sa.Column("scene_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("moment", sa.String(16), nullable=False),
        sa.Column("caption", sa.String(400), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("character_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("location_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_phase_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "moment IN ('arrival','meeting','settled','manual')", name="ck_scene_picture_moment"
        ),
    )
    op.create_index("ix_scene_picture_world", "scene_picture", ["world_id", "created_phase_index"])


def downgrade() -> None:
    op.drop_index("ix_scene_picture_world", table_name="scene_picture")
    op.drop_table("scene_picture")
