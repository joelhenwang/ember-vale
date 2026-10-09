"""Report which stored picture files the sweep would delete. Deletes nothing.

The background loops (API or worker) run the real sweep every few hours
(infrastructure/images/sweep.py, WORLDSIM_IMAGES__SWEEP_*). This dry run
lists files under <assets>/generated that no asset row refers to and that
are older than the grace; the real sweep deletes them once they are still
unused one sweep later.

Run where the assets live. For the compose API container (Git Bash needs
MSYS_NO_PATHCONV=1 so the /app path is not rewritten):

    MSYS_NO_PATHCONV=1 docker compose exec -T \\
        -e PICTURE_SWEEP_ROOT=/app/content/assets api \\
        python - < backend/scripts/picture_sweep.py

Add ``-e PICTURE_SWEEP_LIST=1`` to print every file, and
``-e PICTURE_SWEEP_GRACE_HOURS=1`` to change the grace.
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from pathlib import Path

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.images.sweep import PictureSweeper
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


async def main() -> None:
    root = Path(os.environ.get("PICTURE_SWEEP_ROOT", "../content/assets"))
    grace_h = float(os.environ.get("PICTURE_SWEEP_GRACE_HOURS", "1"))
    engine = create_engine(Settings())
    try:
        sweeper = PictureSweeper(lambda: create_unit_of_work(engine), root, grace_s=grace_h * 3600)
        report = await sweeper.survey()
    finally:
        await engine.dispose()
    if report.refused:
        print(f"refused: {report.refused}")
        return
    if os.environ.get("PICTURE_SWEEP_LIST") == "1":
        for file in sorted(report.unused, key=lambda f: f.ref):
            print(f"{file.size // 1024:>7} KB  {file.ref}")
    folders = Counter(
        "variants" if f.ref.startswith("generated/.variants/") else "originals"
        for f in report.unused
    )
    print(
        f"{report.files} files under generated/: {report.in_use} in use, "
        f"{report.young} younger than {grace_h:g} h, {len(report.unused)} unused "
        f"({folders['originals']} originals, {folders['variants']} variants, "
        f"{report.unused_bytes / 1e6:.1f} MB) would be deleted"
    )


if __name__ == "__main__":
    asyncio.run(main())
