"""A story that goes back to an earlier turn may delete the snapshots of later turns.

Phase snapshots stay immutable: no update, and no delete, except inside a
rewind transaction that says so with the transaction-local setting
``worldsim.rewind = on`` (docs/evidence/rewind-001). The turns it removes
live on as a branch ("the path not taken"), with snapshots of their own.

Merge note: numbered 0060 because a parallel branch may add 0059; re-chain
``down_revision`` onto that one when both land.
"""

from __future__ import annotations

from alembic import op

revision = "0060_rewind_snapshots"
down_revision = "0058_story_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE OR REPLACE FUNCTION forbid_snapshot_mutation() RETURNS trigger AS $$ "
        "BEGIN "
        "IF TG_OP = 'DELETE' AND current_setting('worldsim.rewind', true) = 'on' THEN "
        "RETURN OLD; END IF; "
        "RAISE EXCEPTION 'phase_snapshot is immutable'; END; $$ LANGUAGE plpgsql"
    )


def downgrade() -> None:
    op.execute(
        "CREATE OR REPLACE FUNCTION forbid_snapshot_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'phase_snapshot is immutable'; END; $$ LANGUAGE plpgsql"
    )
