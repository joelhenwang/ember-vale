"""The curated starter art is served as WebP (7.2 MB of PNG became 0.9 MB).

Existing worlds registered the PNG files by content reference; point them
at the WebP copies. The pictures look the same, only the bytes shrink.
"""

from __future__ import annotations

from alembic import op

revision = "0056_starter_art_webp"
down_revision = "0055_picture_repaint"
branch_labels = None
depends_on = None

_FILES = (
    "hearth-background-v1",
    "market-background-v1",
    "wren-portrait-v1",
    "ash-portrait-v1",
)


def upgrade() -> None:
    for name in _FILES:
        op.execute(
            "UPDATE asset_record SET content_ref = 'revamp/" + name + ".webp', "
            "mime = 'image/webp' WHERE content_ref = 'revamp/" + name + ".png'"
        )


def downgrade() -> None:
    for name in _FILES:
        op.execute(
            "UPDATE asset_record SET content_ref = 'revamp/" + name + ".png', "
            "mime = 'image/png' WHERE content_ref = 'revamp/" + name + ".webp'"
        )
