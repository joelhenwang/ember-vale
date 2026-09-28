"""Scene narration source status (duplicate replays must not infer it).

`scene.narration_status` records the `_narrate_scene` outcome
(`narrated`, `fallback`, `failed`, `structured`, `skipped`) atomically
beside the beats, so `_duplicate_report` replays the stored status instead
of reporting `narrated` whenever beats exist. Nullable: legacy rows predate
the record and replay as `unknown`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_scene_narration_status"
down_revision = "0038_preset_creation_receipt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene",
        sa.Column("narration_status", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scene", "narration_status")
