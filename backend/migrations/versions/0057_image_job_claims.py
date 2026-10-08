"""Image jobs are claimed atomically and carry their timing.

``claimed_until`` is a lease: a runner claims one pending job with
``FOR UPDATE SKIP LOCKED`` and pushes the lease forward, so a second
runner (another process, a dedicated worker) never paints the same job.
``created_at`` / ``started_at`` / ``finished_at`` let queue wait and paint
time be measured (perf-llm-001 could not). The ORM row does not map these
columns; only the claim and finish statements touch them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057_image_job_claims"
down_revision = "0056_starter_art_webp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "image_job",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()
        ),
    )
    op.add_column("image_job", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("image_job", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "image_job", sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("image_job", "claimed_until")
    op.drop_column("image_job", "finished_at")
    op.drop_column("image_job", "started_at")
    op.drop_column("image_job", "created_at")
