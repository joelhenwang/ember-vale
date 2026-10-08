"""Image jobs are claimed atomically: two runners never paint the same job."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import text

from worldsim.domain.assets import AssetKind, ImageJob, JobStatus
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def test_runners_claim_different_jobs_and_finishing_ends_the_lease(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            jobs = [
                ImageJob(
                    id=uuid4(),
                    kind=AssetKind.MAP,
                    style_pack_version="anime-saga-v1",
                    idempotency_key=f"claim-test-{n}",
                )
                for n in range(2)
            ]
            async with create_unit_of_work(engine) as uow:
                for job in jobs:
                    await uow.assets.add_job(job)
                await uow.commit()

            async def claim() -> ImageJob | None:
                async with create_unit_of_work(engine) as uow:
                    got = await uow.assets.claim_next_job(600)
                    await uow.commit()
                    return got

            first, second = await asyncio.gather(claim(), claim())
            assert first is not None and second is not None
            assert first.id != second.id
            assert await claim() is None  # both leased: nothing left to take

            async with create_unit_of_work(engine) as uow:
                done = await uow.assets.get_job(first.id)
                await uow.assets.save_job(done.model_copy(update={"status": JobStatus.READY}), 0)
                await uow.commit()
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT claimed_until, started_at, finished_at, created_at "
                            "FROM image_job WHERE id = :id"
                        ),
                        {"id": first.id},
                    )
                ).one()
            assert row.claimed_until is None
            assert row.created_at <= row.started_at <= row.finished_at
        finally:
            await engine.dispose()

    asyncio.run(_inner())
