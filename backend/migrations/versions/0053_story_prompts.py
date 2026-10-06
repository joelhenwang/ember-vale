"""The player's prompt additions: per story (storyteller and images), per character.

Tables of their own, so story creation keeps working against older schemas.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0053_story_prompts"
down_revision = "0052_scene_picture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_prompts",
        sa.Column("world_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("llm_prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("llm_suffix", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_suffix", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("version >= 0", name="ck_story_prompts_version"),
    )
    op.create_table(
        "character_image_prompt",
        sa.Column("character_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("world_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("suffix", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("character_image_prompt")
    op.drop_table("story_prompts")
