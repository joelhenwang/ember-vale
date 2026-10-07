"""Scene pictures get a headline, and moments picked out of the narration."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054_picture_title"
down_revision = "0053_story_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scene_picture", sa.Column("title", sa.String(80), nullable=True))
    op.drop_constraint("ck_scene_picture_moment", "scene_picture", type_="check")
    op.create_check_constraint(
        "ck_scene_picture_moment",
        "scene_picture",
        "moment IN ('arrival','meeting','settled','turning','manual')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scene_picture_moment", "scene_picture", type_="check")
    op.execute("DELETE FROM scene_picture WHERE moment = 'turning'")
    op.create_check_constraint(
        "ck_scene_picture_moment",
        "scene_picture",
        "moment IN ('arrival','meeting','settled','manual')",
    )
    op.drop_column("scene_picture", "title")
