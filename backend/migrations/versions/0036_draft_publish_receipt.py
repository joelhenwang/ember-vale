"""Publication receipts for editor drafts (E3 correction).

A published draft records which draft version produced which revision
under which content, so an identical publish retry replays the
original revision instead of conflicting or duplicating — even after
later revisions exist.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_draft_publish_receipt"
down_revision = "0035_editor_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "editor_draft",
        sa.Column("published_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "editor_draft",
        sa.Column("published_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "editor_draft",
        sa.Column("published_hash", sa.String(length=128), nullable=True),
    )
    # Durable publication log: survives draft completion so a late
    # identical retry still replays its revision. Keyed by draft:
    # versions only advance when fields change, so the recorded version
    # identifies the exact request.
    op.create_table(
        "editor_publication",
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("draft_version >= 1", name="ck_editor_publication_version"),
        sa.CheckConstraint("revision >= 1", name="ck_editor_publication_revision"),
        sa.PrimaryKeyConstraint("draft_id"),
    )
    op.create_index("ix_editor_publication_preset", "editor_publication", ["preset_id"])


def downgrade() -> None:
    op.drop_index("ix_editor_publication_preset", table_name="editor_publication")
    op.drop_table("editor_publication")
    op.drop_column("editor_draft", "published_hash")
    op.drop_column("editor_draft", "published_revision")
    op.drop_column("editor_draft", "published_version")
