"""Place spans the local model found in a line, cached by the line's hash.

The director reads these instead of waiting on the model (about 160 ms
a line); a background reader fills the cache from speech, attempts,
intentions and rumours. ``model`` carries the label set too, so a label
change reads everything again beside the old rows.
"""

from __future__ import annotations

from alembic import op

revision = "0049_place_mention"
down_revision = "0048_recall_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE place_mention (
            text_hash char(64) NOT NULL,
            model varchar(96) NOT NULL,
            places jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_place_mention PRIMARY KEY (text_hash, model)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE place_mention")
