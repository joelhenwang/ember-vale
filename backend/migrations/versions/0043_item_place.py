"""Items can lie at a place and carry their own name.

``location_id`` holds where an unheld item lies (a dropped locket at the
Market); ``name``/``description`` describe one-off items outside the
catalog, such as those a director opening places.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0043_item_place"
down_revision = "0042_character_intention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_instance", sa.Column("location_id", PG_UUID(as_uuid=True), nullable=True))
    op.add_column("item_instance", sa.Column("name", sa.String(128), nullable=True))
    op.add_column("item_instance", sa.Column("description", sa.String(600), nullable=True))
    op.create_foreign_key("fk_item_location", "item_instance", "location", ["location_id"], ["id"])
    op.create_index("ix_item_instance_location_id", "item_instance", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_item_instance_location_id", table_name="item_instance")
    op.drop_constraint("fk_item_location", "item_instance", type_="foreignkey")
    op.drop_column("item_instance", "description")
    op.drop_column("item_instance", "name")
    op.drop_column("item_instance", "location_id")
