"""Picture files no asset row refers to any more are swept, carefully."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from test_images import PACKS, PNG, _Painter, _story  # pyright: ignore[reportPrivateUsage]
from test_images import client as client  # the fixture
from test_stage1_api import ApiClient

from worldsim.application.ports.images import GeneratedImage, ImageRequest
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind, AssetRecord
from worldsim.domain.ids import new_asset_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.images.runner import ImageJobRunner
from worldsim.infrastructure.images.sweep import PictureSweeper, SweepReport
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.storage.local import LocalStorage

HOUR = 3600.0
NOW = 1_900_000_000.0


def _file(root: Path, ref: str, age_s: float, data: bytes = PNG) -> Path:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (NOW - age_s, NOW - age_s))
    return path


def _asset(ref: str, world_id: UUID | None = None) -> AssetRecord:
    return AssetRecord(
        id=new_asset_id(),
        world_id=world_id,
        kind=AssetKind.SCENE,
        content_ref=ref,
        mime="image/png",
        width=64,
        height=64,
        style_pack_version="anime-saga-v1",
    )


async def _sweeps(root: Path, rows: list[AssetRecord], times: list[float]) -> list[SweepReport]:
    """Add the rows, then sweep once at each time."""
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            for row in rows:
                await uow.assets.add_asset(row)
            await uow.commit()
        clock = iter(times)
        sweeper = PictureSweeper(
            lambda: create_unit_of_work(engine), root, clock=lambda: next(clock)
        )
        return [await sweeper.sweep_once() for _ in times]
    finally:
        await engine.dispose()


def test_only_long_unused_generated_files_go(migrated_db: None, tmp_path: Path) -> None:
    world_a, world_b = UUID(int=1), UUID(int=2)
    kept_asset = _asset("generated/a/scene-kept.png", world_a)
    rows = [
        kept_asset,
        # A branch shares its story's file through its own row.
        _asset("generated/a/scene-shared.png", world_b),
        # Library pictures have no world.
        _asset("generated/maps/library-map.webp"),
        # Case differences never cost a file.
        _asset("generated/a/Scene-Case.PNG", world_a),
    ]
    old = 3 * HOUR
    keep = [
        _file(tmp_path, "generated/a/scene-kept.png", old),
        _file(tmp_path, "generated/a/scene-shared.png", old),
        _file(tmp_path, "generated/maps/library-map.webp", old),
        _file(tmp_path, "generated/a/scene-case.png", old),
        _file(tmp_path, f"generated/.variants/{kept_asset.id.hex}-w320.webp", old),
        # Too young: a job may be writing it before its row commits.
        _file(tmp_path, "generated/a/scene-just-painted.png", 10 * 60),
        # Outside generated/: the starter art is never looked at.
        _file(tmp_path, "revamp/unlisted.webp", old),
    ]
    gone = [
        _file(tmp_path, "generated/a/scene-rewound.png", old, b"x" * 1000),
        _file(tmp_path, f"generated/.variants/{UUID(int=99).hex}-w640.webp", old),
        _file(tmp_path, "generated/a/.scene-x.png.1a2b3c4d.part", old),
    ]
    first, second, third = asyncio.run(
        _sweeps(tmp_path, rows, [NOW, NOW + 6 * HOUR, NOW + 12 * HOUR])
    )
    # The first sweep only notes what is unused; nothing goes yet.
    assert (first.deleted, first.waiting, first.young) == (0, 3, 1)
    assert first.in_use == 5
    # Still unused one sweep later: now they go.
    assert (second.deleted, second.failed) == (3, 0)
    assert second.bytes_freed == 1000 + 2 * len(PNG)
    # The young file aged into the waiting list, and goes one sweep later.
    assert second.waiting == 1 and third.deleted == 1
    assert all(p.exists() for p in keep[:5] + keep[6:]) and not any(p.exists() for p in gone)


def test_a_file_used_again_before_the_second_sweep_stays(migrated_db: None, tmp_path: Path) -> None:
    path = _file(tmp_path, "generated/a/scene-back.png", 3 * HOUR)

    async def run() -> tuple[SweepReport, SweepReport]:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                await uow.assets.add_asset(_asset("generated/a/other.png"))
                await uow.commit()
            clock = iter([NOW, NOW + 6 * HOUR])
            sweeper = PictureSweeper(
                lambda: create_unit_of_work(engine), tmp_path, clock=lambda: next(clock)
            )
            first = await sweeper.sweep_once()
            async with create_unit_of_work(engine) as uow:
                await uow.assets.add_asset(_asset("generated/a/scene-back.png"))
                await uow.commit()
            return first, await sweeper.sweep_once()
        finally:
            await engine.dispose()

    first, second = asyncio.run(run())
    assert first.waiting == 1 and (second.deleted, second.in_use) == (0, 1)
    assert path.exists()


class _NoRows:
    async def stored_refs(self) -> list[tuple[UUID, str]]:
        return []


@asynccontextmanager
async def _empty_database() -> AsyncGenerator[Any]:
    class _Uow:
        assets = _NoRows()

    yield _Uow()


def test_an_empty_database_deletes_nothing(tmp_path: Path) -> None:
    path = _file(tmp_path, "generated/a/scene.png", 30 * HOUR)
    clock = iter([NOW, NOW + 6 * HOUR])
    sweeper = PictureSweeper(
        cast("Callable[[], UnitOfWork]", _empty_database), tmp_path, clock=lambda: next(clock)
    )

    async def run() -> list[SweepReport]:
        return [await sweeper.sweep_once(), await sweeper.sweep_once()]

    reports = asyncio.run(run())
    assert all(r.refused and r.deleted == 0 for r in reports)
    assert path.exists()


class _RemovedWhilePainting(_Painter):
    """The story's jobs are removed (a rewind, say) while the picture is painted."""

    def __init__(self, world_id: UUID) -> None:
        super().__init__()
        self._world_id = world_id

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        if not self.requests:
            engine = create_engine(Settings())
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        text("DELETE FROM image_job WHERE world_id = :w"), {"w": self._world_id}
                    )
            finally:
                await engine.dispose()
        return await super().generate(request)


def test_a_job_removed_while_painting_leaves_only_a_file_for_the_sweep(
    client: ApiClient, tmp_path: Path
) -> None:
    world_id = _story(client)

    async def run() -> tuple[bool, int, int, list[Path], SweepReport, SweepReport]:
        engine = create_engine(Settings())
        try:
            runner = ImageJobRunner(
                lambda: create_unit_of_work(engine),
                _RemovedWhilePainting(world_id),
                LocalStorage(tmp_path),
                PACKS,
                world_id=world_id,
            )
            worked = await runner.run_once()  # must not raise
            assert not await runner.run_once()  # nothing left to paint
            async with engine.connect() as conn:
                jobs = (
                    await conn.execute(
                        text("SELECT count(*) FROM image_job WHERE world_id = :w"),
                        {"w": world_id},
                    )
                ).scalar_one()
                assets = (
                    await conn.execute(
                        text(
                            "SELECT count(*) FROM asset_record WHERE world_id = :w"
                            " AND kind = 'portrait'"
                        ),
                        {"w": world_id},
                    )
                ).scalar_one()
            files = list((tmp_path / "generated").rglob("*.*"))
            later = files[0].stat().st_mtime + 2 * HOUR
            clock = iter([later, later + 6 * HOUR])
            sweeper = PictureSweeper(
                lambda: create_unit_of_work(engine), tmp_path, clock=lambda: next(clock)
            )
            return (
                worked,
                jobs,
                assets,
                files,
                await sweeper.sweep_once(),
                await sweeper.sweep_once(),
            )
        finally:
            await engine.dispose()

    worked, jobs, assets, files, first, second = asyncio.run(run())
    # Nothing came back: no job, no asset row, just the painted file.
    assert worked and (jobs, assets) == (0, 0)
    assert len(files) == 1 and f"generated/{world_id}/portrait-" in files[0].as_posix()
    assert first.waiting == 1 and second.deleted == 1
    assert not files[0].exists()
