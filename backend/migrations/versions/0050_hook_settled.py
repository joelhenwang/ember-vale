"""Event effects may settle an open rumour a successful attempt finished."""

from __future__ import annotations

from alembic import op

revision = "0050_hook_settled"
down_revision = "0049_place_mention"
branch_labels = None
depends_on = None

_TYPES = (
    "'advance_clock','move_entity','resource_adjusted','record_observation',"
    "'record_memory','skill_progress','deity_override','item_found'"
)


def upgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint(
        "ck_effect_type", "event_effect", f"effect_type IN ({_TYPES},'hook_settled')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_effect_type", "event_effect", type_="check")
    op.create_check_constraint("ck_effect_type", "event_effect", f"effect_type IN ({_TYPES})")
