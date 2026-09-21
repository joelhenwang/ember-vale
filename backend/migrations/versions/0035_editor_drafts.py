"""Durable editor drafts for preset revisions (E3).

One partial draft per preset, versioned for optimistic concurrency.
Draft saves stay lenient; publishing merges the draft over its base
revision and validates the strict preset schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_editor_drafts"
down_revision = "0034_step_effect_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editor_draft",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "preset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("preset.id", name="fk_editor_draft_preset"),
            nullable=False,
        ),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("base_revision >= 1", name="ck_editor_draft_base"),
        sa.CheckConstraint("version >= 1", name="ck_editor_draft_version"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preset_id", name="uq_editor_draft_preset"),
    )
    op.create_index("ix_editor_draft_preset", "editor_draft", ["preset_id"])


def downgrade() -> None:
    op.drop_index("ix_editor_draft_preset", table_name="editor_draft")
    op.drop_table("editor_draft")
