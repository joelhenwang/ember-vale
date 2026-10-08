"""Scene pictures can be repainted from a prompt the player edited."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0055_picture_repaint"
down_revision = "0054_picture_title"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_picture",
        sa.Column("raw_prompt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("scene_picture", sa.Column("repaint_job_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("scene_picture", "repaint_job_id")
    op.drop_column("scene_picture", "raw_prompt")
