"""Observation source identity (narration dedup must not use fact keys).

`observation.source_id` carries the stable underlying action identity (the
intent id) when an observation's facts derive from one action. Nullable:
legacy rows predate the record and keep every fact, as before.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0040_observation_source"
down_revision = "0039_scene_narration_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "observation",
        sa.Column("source_id", PG_UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("observation", "source_id")
