"""Embeddings of what characters perceived and remember, for recall by relevance.

One row per context source (``obs:<id>:<key>`` or ``mem:<id>``) and
embedding model, so a model change re-indexes beside the old vectors
instead of mixing spaces. The text rides along so a row older than the
recent window can come back into context without another lookup. The
vector column carries no fixed dimension; lookups are per owner and
small, so there is no ANN index yet.
"""

from __future__ import annotations

from alembic import op

revision = "0048_recall_vector"
down_revision = "0047_item_found"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recall_vector (
            source_id varchar(160) NOT NULL,
            model varchar(96) NOT NULL,
            world_id uuid NOT NULL REFERENCES world(id) ON DELETE CASCADE,
            owner_character_id uuid NOT NULL REFERENCES character(id) ON DELETE CASCADE,
            created_phase_index integer NOT NULL,
            text varchar(2000) NOT NULL,
            embedding vector NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_recall_vector PRIMARY KEY (source_id, model)
        )
        """
    )
    op.execute("CREATE INDEX ix_recall_vector_owner ON recall_vector (owner_character_id, model)")


def downgrade() -> None:
    op.execute("DROP TABLE recall_vector")
