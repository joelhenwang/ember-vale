"""Model profiles may name the Venice adapter."""

from __future__ import annotations

from alembic import op

revision = "0045_venice_adapter"
down_revision = "0044_card_pronouns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_profile_adapter", "model_profile", type_="check")
    op.create_check_constraint(
        "ck_profile_adapter", "model_profile", "adapter IN ('fake','openrouter','venice')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_profile_adapter", "model_profile", type_="check")
    op.create_check_constraint(
        "ck_profile_adapter", "model_profile", "adapter IN ('fake','openrouter')"
    )
