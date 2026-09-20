"""Preset revision repair: corrected starter as revision 2.

Revision 1 of a preset plus its content must stay stable: 0032 rewrote the
world builtin rev 1 payload in place, so drafts pinned to rev 1 can resolve
differently before/after migration. This repair:

- restores a 0032-mutated world rev 1 to its exact 0030 seed content
  (travel [], hash 'builtin-v1'); untouched originals are left alone and any
  other rev 1 content is never overwritten;
- publishes world rev 2 (Hearth <-> Market directed legs) and template rev 2
  (pins world rev 2) with frozen canonical content hashes;
- points both builtins' current_revision at 2.

Character and style presets are unchanged. Downgrade removes the rev 2 rows
and resets current_revision to 1; it deliberately does not touch rev 1
content (it must not re-mutate history either way).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_preset_travel_rev2"
down_revision = "0032_starter_travel"
branch_labels = None
depends_on = None

WORLD_PRESET_ID = "20000000-0000-4000-8000-000000000001"
TEMPLATE_PRESET_ID = "20000000-0000-4000-8000-000000000301"

WORLD_REV1_ORIGINAL = (
    '{"kind": "world", "name": "Ember Vale", '
    '"description": "A sheltered vale of hearths, markets, and old roads.", '
    '"lore": "The vale keeps its stories close.", '
    '"locations": [{"key": "hearth", "name": "Hearth"}, '
    '{"key": "market", "name": "Market"}], "travel": [], '
    '"starting_location_key": "hearth", "default_cast": ["wren", "ash"], '
    '"style_pack_id": "anime-saga-v1"}'
)

WORLD_REV2_PAYLOAD = (
    '{"kind": "world", "name": "Ember Vale", '
    '"description": "A sheltered vale of hearths, markets, and old roads.", '
    '"lore": "The vale keeps its stories close.", '
    '"locations": [{"key": "hearth", "name": "Hearth"}, '
    '{"key": "market", "name": "Market"}], '
    '"travel": [["hearth", "market"], ["market", "hearth"]], '
    '"starting_location_key": "hearth", "default_cast": ["wren", "ash"], '
    '"style_pack_id": "anime-saga-v1"}'
)
WORLD_REV2_HASH = "06f664c3a14328c10b72178d9371dbfae900750b5355e21acbcf51b118af78b6"

TEMPLATE_REV2_PAYLOAD = (
    '{"kind": "template", "display_name": "Ember Vale opening", '
    f'"world_preset_id": "{WORLD_PRESET_ID}", "world_preset_revision": 2, '
    f'"cast_preset_ids": ["20000000-0000-4000-8000-000000000101", '
    f'"20000000-0000-4000-8000-000000000102"], '
    '"tone": "hopeful mystery", "pacing": "measured"}'
)
TEMPLATE_REV2_HASH = "d2dc3b8fb7bf5af1024bb981224f6a1adb9037956854a4f1575ea380b215afa2"


def _uuid(value: str):
    return uuid.UUID(value)


def upgrade() -> None:
    # 1. Restore a 0032-mutated world rev 1 to exact 0030 content.
    op.execute(
        sa.text(
            "UPDATE preset_revision SET payload = CAST(:original AS JSONB), "
            "content_hash = 'builtin-v1' WHERE preset_id = :id AND revision = 1 "
            "AND content_hash = 'builtin-v2' "
            "AND payload->'travel' = CAST(:fixed_travel AS JSONB)"
        ).bindparams(
            sa.bindparam(
                "id", type_=postgresql.UUID(as_uuid=True), value=_uuid(WORLD_PRESET_ID)
            ),
            original=WORLD_REV1_ORIGINAL,
            fixed_travel='[["hearth", "market"], ["market", "hearth"]]',
        )
    )
    # 2. Publish rev 2 rows when missing (repeatable, never rewrite).
    for preset_id, payload, content_hash in (
        (WORLD_PRESET_ID, WORLD_REV2_PAYLOAD, WORLD_REV2_HASH),
        (TEMPLATE_PRESET_ID, TEMPLATE_REV2_PAYLOAD, TEMPLATE_REV2_HASH),
    ):
        op.execute(
            sa.text(
                "INSERT INTO preset_revision (preset_id, revision, schema_version, "
                "payload, content_hash, created_at) SELECT :id, 2, 1, "
                "CAST(:payload AS JSONB), :content_hash, now() "
                "WHERE NOT EXISTS (SELECT 1 FROM preset_revision "
                "WHERE preset_id = :id AND revision = 2)"
            ).bindparams(
                sa.bindparam(
                    "id", type_=postgresql.UUID(as_uuid=True), value=_uuid(preset_id)
                ),
                payload=payload,
                content_hash=content_hash,
            )
        )
    # 3. Point current_revision at 2 wherever rev 2 now exists.
    op.execute(
        sa.text(
            "UPDATE preset SET current_revision = 2 WHERE id IN (:world, :template) "
            "AND EXISTS (SELECT 1 FROM preset_revision "
            "WHERE preset_revision.preset_id = preset.id AND revision = 2)"
        ).bindparams(
            sa.bindparam(
                "world", type_=postgresql.UUID(as_uuid=True), value=_uuid(WORLD_PRESET_ID)
            ),
            sa.bindparam(
                "template",
                type_=postgresql.UUID(as_uuid=True),
                value=_uuid(TEMPLATE_PRESET_ID),
            ),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM preset_revision WHERE revision = 2 AND preset_id IN "
            "(:world, :template)"
        ).bindparams(
            sa.bindparam(
                "world", type_=postgresql.UUID(as_uuid=True), value=_uuid(WORLD_PRESET_ID)
            ),
            sa.bindparam(
                "template",
                type_=postgresql.UUID(as_uuid=True),
                value=_uuid(TEMPLATE_PRESET_ID),
            ),
        )
    )
    op.execute(
        sa.text(
            "UPDATE preset SET current_revision = 1 WHERE id IN (:world, :template)"
        ).bindparams(
            sa.bindparam(
                "world", type_=postgresql.UUID(as_uuid=True), value=_uuid(WORLD_PRESET_ID)
            ),
            sa.bindparam(
                "template",
                type_=postgresql.UUID(as_uuid=True),
                value=_uuid(TEMPLATE_PRESET_ID),
            ),
        )
    )
