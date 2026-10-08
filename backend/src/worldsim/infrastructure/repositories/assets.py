"""Visual asset and image-job adapter (owned by REVAMP-P04)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.assets import AssetKind, AssetRecord, AssetStatus, ImageJob, JobStatus
from worldsim.domain.ids import AssetId, ImageJobId
from worldsim.infrastructure.models.assets import AssetRow, ImageJobRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_asset(self, row: AssetRow) -> AssetRecord:
        return AssetRecord(
            id=row.id,
            world_id=row.world_id,
            kind=AssetKind(row.kind),
            subject_id=row.subject_id,
            content_ref=row.content_ref,
            mime=row.mime,
            width=row.width,
            height=row.height,
            style_pack_version=row.style_pack_version,
            subject_visual_version=row.subject_visual_version,
            status=AssetStatus(row.status),
            version=row.version,
        )

    def _to_job(self, row: ImageJobRow) -> ImageJob:
        return ImageJob(
            id=row.id,
            world_id=row.world_id,
            kind=AssetKind(row.kind),
            subject_id=row.subject_id,
            style_pack_version=row.style_pack_version,
            idempotency_key=row.idempotency_key,
            status=JobStatus(row.status),
            attempt_count=row.attempt_count,
            result_asset_id=row.result_asset_id,
            error=row.error,
            version=row.version,
        )

    async def add_asset(self, asset: AssetRecord) -> None:
        self._session.add(
            AssetRow(
                id=asset.id,
                world_id=asset.world_id,
                kind=asset.kind.value,
                subject_id=asset.subject_id,
                content_ref=asset.content_ref,
                mime=asset.mime,
                width=asset.width,
                height=asset.height,
                style_pack_version=asset.style_pack_version,
                subject_visual_version=asset.subject_visual_version,
                status=asset.status.value,
                version=asset.version,
            )
        )
        await self._session.flush()

    async def get_asset(self, asset_id: AssetId) -> AssetRecord:
        row = await self._session.get(AssetRow, asset_id)
        if row is None:
            raise missing("asset", asset_id)
        return self._to_asset(row)

    async def find_asset_by_ref(
        self, world_id: UUID | None, content_ref: str
    ) -> AssetRecord | None:
        row = (
            await self._session.execute(
                select(AssetRow).where(
                    AssetRow.world_id == world_id,
                    AssetRow.content_ref == content_ref,
                )
            )
        ).scalar_one_or_none()
        return self._to_asset(row) if row is not None else None

    async def list_assets_for_subject(
        self, world_id: UUID, kind: str, subject_id: UUID
    ) -> list[AssetRecord]:
        rows = (
            await self._session.execute(
                select(AssetRow)
                .where(
                    AssetRow.world_id == world_id,
                    AssetRow.kind == kind,
                    AssetRow.subject_id == subject_id,
                )
                .order_by(AssetRow.subject_visual_version.desc())
            )
        ).scalars()
        return [self._to_asset(row) for row in rows]

    async def list_ready_for_world(self, world_id: UUID, kind: str) -> list[AssetRecord]:
        rows = (
            await self._session.execute(
                select(AssetRow)
                .where(
                    AssetRow.world_id == world_id,
                    AssetRow.kind == kind,
                    AssetRow.status == "ready",
                )
                .order_by(AssetRow.subject_visual_version.desc())
            )
        ).scalars()
        return [self._to_asset(row) for row in rows]

    async def list_unscoped(self, kind: str) -> list[AssetRecord]:
        rows = (
            await self._session.execute(
                select(AssetRow)
                .where(
                    AssetRow.world_id.is_(None),
                    AssetRow.kind == kind,
                    AssetRow.status == "ready",
                )
                .order_by(AssetRow.subject_visual_version.desc())
            )
        ).scalars()
        return [self._to_asset(row) for row in rows]

    async def add_job(self, job: ImageJob) -> None:
        self._session.add(
            ImageJobRow(
                id=job.id,
                world_id=job.world_id,
                kind=job.kind.value,
                subject_id=job.subject_id,
                style_pack_version=job.style_pack_version,
                idempotency_key=job.idempotency_key,
                status=job.status.value,
                attempt_count=job.attempt_count,
                result_asset_id=job.result_asset_id,
                error=job.error,
                version=job.version,
            )
        )
        await self._session.flush()

    async def get_job(self, job_id: ImageJobId) -> ImageJob:
        row = await self._session.get(ImageJobRow, job_id)
        if row is None:
            raise missing("image job", job_id)
        return self._to_job(row)

    async def get_jobs(self, job_ids: list[UUID]) -> dict[UUID, ImageJob]:
        """Many image jobs in one query (missing ids are left out)."""
        if not job_ids:
            return {}
        rows = (
            (await self._session.execute(select(ImageJobRow).where(ImageJobRow.id.in_(job_ids))))
            .scalars()
            .all()
        )
        return {row.id: self._to_job(row) for row in rows}

    async def find_job_by_key(self, world_id: UUID | None, key: str) -> ImageJob | None:
        row = (
            await self._session.execute(
                select(ImageJobRow).where(
                    ImageJobRow.world_id == world_id,
                    ImageJobRow.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        return self._to_job(row) if row is not None else None

    async def list_pending_jobs(self, limit: int, world_id: UUID | None = None) -> list[ImageJob]:
        """Pending jobs, fewest attempts first so one stuck job cannot starve others."""
        query = select(ImageJobRow).where(ImageJobRow.status == JobStatus.PENDING.value)
        if world_id is not None:
            query = query.where(ImageJobRow.world_id == world_id)
        rows = (
            await self._session.execute(
                query.order_by(ImageJobRow.attempt_count, ImageJobRow.id).limit(limit)
            )
        ).scalars()
        return [self._to_job(row) for row in rows]

    async def claim_next_job(
        self, lease_seconds: int, world_id: UUID | None = None
    ) -> ImageJob | None:
        """Claim one pending job for this runner, or None.

        One statement: the row is locked with SKIP LOCKED and its lease
        pushed forward, so concurrent runners (processes) never take the
        same job. An expired lease (a runner died mid-paint) is claimable
        again. Commit to make the claim visible to others.
        """
        where_world = "AND world_id = :world" if world_id is not None else ""
        claimed = (
            await self._session.execute(
                text(
                    "UPDATE image_job SET claimed_until = now() + make_interval(secs => :lease), "
                    "started_at = coalesce(started_at, now()) "
                    "WHERE id = (SELECT id FROM image_job WHERE status = 'pending' "
                    "AND (claimed_until IS NULL OR claimed_until < now()) "
                    f"{where_world} ORDER BY attempt_count, id "
                    "FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id"
                ),
                {"lease": lease_seconds, "world": world_id},
            )
        ).scalar_one_or_none()
        if claimed is None:
            return None
        row = await self._session.get(ImageJobRow, claimed, populate_existing=True)
        return self._to_job(row) if row is not None else None

    async def style_pack_for_world(self, world_id: UUID) -> str | None:
        return (
            await self._session.execute(
                select(ImageJobRow.style_pack_version)
                .where(ImageJobRow.world_id == world_id)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def save_job(self, job: ImageJob, expected_version: int) -> ImageJob:
        row = await self._session.get(ImageJobRow, job.id)
        if row is None:
            raise missing("image job", job.id)
        if row.version != expected_version:
            raise version_conflict("image job", job.id, expected_version, row.version)
        row.status = job.status.value
        row.attempt_count = job.attempt_count
        row.result_asset_id = job.result_asset_id
        row.error = job.error
        row.version = expected_version + 1
        await self._session.flush()
        # The lease ends with any outcome; a finished job keeps its time.
        await self._session.execute(
            text(
                "UPDATE image_job SET claimed_until = NULL, finished_at = CASE "
                "WHEN status = 'pending' THEN NULL ELSE now() END WHERE id = :id"
            ),
            {"id": job.id},
        )
        return self._to_job(row)
