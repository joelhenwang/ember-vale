"""Idempotent preset first-publication receipts (E3 studio wiring).

`preset_creation_receipt` records which client key created which preset
under which request hash. The receipt, the preset, and its first
revision commit atomically, so a lost response can be retried safely:
the same key plus the same request replays the same preset, while the
same key with different content conflicts.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_preset_creation_receipt"
down_revision = "0037_publication_per_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preset_creation_receipt",
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("created_preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_preset_id"], ["preset.id"], name="fk_preset_receipt_preset"
        ),
        sa.PrimaryKeyConstraint("operator", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("preset_creation_receipt")
