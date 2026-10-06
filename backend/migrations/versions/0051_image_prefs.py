"""Image preferences (Krea fields) live with the operator's other preferences."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0051_image_prefs"
down_revision = "0050_hook_settled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_preferences",
        sa.Column("images", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("application_preferences", "images")
