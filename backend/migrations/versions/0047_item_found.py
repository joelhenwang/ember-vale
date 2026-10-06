"""Event effects may record an item a successful attempt found."""

from __future__ import annotations

from alembic import op

revision = "0047_item_found"
down_revision = "0046_hook_ending"
branch_labels = None
depends_on = None

_TYPES = (
    "'advance_clock','move_entity','resource_adjusted','record_observation',"
    "'record_memory','skill_progress','deity_override'"
)


def upgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint(
        "ck_effect_type", "event_effect", f"effect_type IN ({_TYPES},'item_found')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint("ck_effect_type", "event_effect", f"effect_type IN ({_TYPES})")
