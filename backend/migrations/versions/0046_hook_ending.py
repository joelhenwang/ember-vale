"""Hooks can close with an ending, so rumours resolve and new ones can start."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_hook_ending"
down_revision = "0045_venice_adapter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "narrative_hook",
        sa.Column("ending", sa.String(240), nullable=False, server_default=""),
    )
    op.add_column("narrative_hook", sa.Column("closed_phase_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("narrative_hook", "closed_phase_index")
    op.drop_column("narrative_hook", "ending")
