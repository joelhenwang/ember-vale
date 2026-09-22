"""Publication receipts per draft version (E3 correction).

A draft can publish, accept more edits, and publish again: each
published draft version keeps its own receipt, so the first
publication still replays after the second lands. The key becomes
(draft_id, draft_version); explicit discard still voids every receipt
for the draft.

A matching draft version implies matching fields — every successful
save advances the version, so fields cannot change without one — and
the recorded version identifies the exact published request.
"""

from __future__ import annotations

from alembic import op

revision = "0037_publication_per_version"
down_revision = "0036_draft_publish_receipt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0036 created this primary key unnamed, so the shared naming
    # convention called it pk_editor_publication.
    op.drop_constraint(
        "pk_editor_publication", "editor_publication", type_="primary"
    )
    op.create_primary_key(
        "pk_editor_publication",
        "editor_publication",
        ["draft_id", "draft_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "pk_editor_publication", "editor_publication", type_="primary"
    )
    op.create_primary_key(
        "pk_editor_publication", "editor_publication", ["draft_id"]
    )
