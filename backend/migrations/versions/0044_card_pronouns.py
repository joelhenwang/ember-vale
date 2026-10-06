"""Character cards and character presets can say how to refer to someone.

Empty means unstated; existing cards keep that default.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_card_pronouns"
down_revision = "0043_item_place"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "character_card_version",
        sa.Column("pronouns", sa.String(40), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("character_card_version", "pronouns")
