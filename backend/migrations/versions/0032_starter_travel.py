"""Starter travel: Hearth <-> Market legs on the world builtin seed.

Seed-content correction (not user data): the 0030 builtin world payload
shipped with `"travel": []`, so story creation could never materialize a
Hearth/Market route and travel validation always failed. This sets the
intended directed pairs on revision 1, matching
`application/library/builtins.py`. Only rows still carrying the empty seed
travel are touched; downgrade restores it.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_starter_travel"
down_revision = "0031_settings_pipeline"
branch_labels = None
depends_on = None

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"

FIXED_TRAVEL = '[["hearth", "market"], ["market", "hearth"]]'


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE preset_revision SET payload = jsonb_set(payload, '{travel}', "
            "CAST(:travel AS JSONB)), content_hash = 'builtin-v2' "
            "WHERE preset_id = :id AND revision = 1 AND payload->'travel' = '[]'"
        ).bindparams(
            sa.bindparam(
                "id",
                type_=postgresql.UUID(as_uuid=True),
                value=uuid.UUID(WORLD_PRESET_ID),
            ),
            travel=FIXED_TRAVEL,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE preset_revision SET payload = jsonb_set(payload, '{travel}', "
            "'[]'), content_hash = 'builtin-v1' "
            "WHERE preset_id = :id AND revision = 1 AND payload->'travel' = "
            "CAST(:travel AS JSONB)"
        ).bindparams(
            sa.bindparam(
                "id",
                type_=postgresql.UUID(as_uuid=True),
                value=uuid.UUID(WORLD_PRESET_ID),
            ),
            travel=FIXED_TRAVEL,
        )
    )
