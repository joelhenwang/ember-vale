"""Library preset and immutable revision adapter."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError as SqlIntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import EditorDraftId
from worldsim.domain.presets import (
    EditorDraft,
    EditorPublication,
    Preset,
    PresetCreationReceipt,
    PresetKind,
    PresetRevision,
)
from worldsim.infrastructure.models.stories import (
    EditorDraftRow,
    EditorPublicationRow,
    PresetCreationReceiptRow,
    PresetRevisionRow,
    PresetRow,
)
from worldsim.infrastructure.repositories._common import (
    missing,
    unique_violation,
    version_conflict,
)


class SqlAlchemyPresetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_preset(self, row: PresetRow) -> Preset:
        return Preset(
            id=row.id,
            kind=PresetKind(row.kind),
            name=row.name,
            builtin=row.builtin,
            readonly=row.readonly,
            archived_at=row.archived_at,
            current_revision=row.current_revision,
            version=row.version,
            created_at=row.created_at,
        )

    def _to_revision(self, row: PresetRevisionRow) -> PresetRevision:
        return PresetRevision.model_validate(
            {
                "preset_id": row.preset_id,
                "revision": row.revision,
                "schema_version": row.schema_version,
                "payload": row.payload,
                "content_hash": row.content_hash,
                "created_at": row.created_at,
            }
        )

    async def add_preset(self, preset: Preset) -> None:
        self._session.add(
            PresetRow(
                id=preset.id,
                kind=preset.kind.value,
                name=preset.name,
                builtin=preset.builtin,
                readonly=preset.readonly,
                archived_at=preset.archived_at,
                current_revision=preset.current_revision,
                version=preset.version,
                created_at=preset.created_at,
            )
        )
        await self._session.flush()

    async def get_preset(self, preset_id: UUID) -> Preset:
        preset = await self.find_preset(preset_id)
        if preset is None:
            raise missing("preset", preset_id)
        return preset

    async def find_preset(self, preset_id: UUID) -> Preset | None:
        row = await self._session.get(PresetRow, preset_id)
        return self._to_preset(row) if row is not None else None

    async def list_presets(
        self, *, kind: str | None = None, include_archived: bool = False, limit: int = 100
    ) -> list[Preset]:
        query = select(PresetRow).order_by(PresetRow.name, PresetRow.id)
        if kind is not None:
            query = query.where(PresetRow.kind == kind)
        if not include_archived:
            query = query.where(PresetRow.archived_at.is_(None))
        query = query.limit(max(1, min(limit, 100)))
        rows = (await self._session.execute(query)).scalars().all()
        return [self._to_preset(row) for row in rows]

    async def save_preset(self, preset: Preset, expected_version: int) -> Preset:
        row = await self._session.get(PresetRow, preset.id)
        if row is None:
            raise missing("preset", preset.id)
        if row.readonly:
            raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
        if row.version != expected_version:
            raise version_conflict("preset", preset.id, expected_version, row.version)
        row.name = preset.name
        row.archived_at = preset.archived_at
        row.current_revision = preset.current_revision
        row.version = expected_version + 1
        await self._session.flush()
        return preset.model_copy(update={"version": expected_version + 1})

    async def set_archived(
        self, preset_id: UUID, archived_at: datetime | None, expected_version: int
    ) -> Preset:
        row = await self._session.get(PresetRow, preset_id)
        if row is None:
            raise missing("preset", preset_id)
        if row.version != expected_version:
            raise version_conflict("preset", preset_id, expected_version, row.version)
        row.archived_at = archived_at
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_preset(row)

    async def add_revision(self, revision: PresetRevision) -> None:
        self._session.add(
            PresetRevisionRow(
                preset_id=revision.preset_id,
                revision=revision.revision,
                schema_version=revision.schema_version,
                payload=revision.payload.model_dump(mode="json"),
                content_hash=revision.content_hash,
                created_at=revision.created_at,
            )
        )
        await self._session.flush()

    async def get_revision(self, preset_id: UUID, revision: int) -> PresetRevision:
        row = await self._session.get(PresetRevisionRow, (preset_id, revision))
        if row is None:
            raise missing("preset revision", preset_id)
        return self._to_revision(row)

    def _to_editor_draft(self, row: EditorDraftRow) -> EditorDraft:
        return EditorDraft(
            id=row.id,
            preset_id=row.preset_id,
            base_revision=row.base_revision,
            fields=dict(row.fields),
            version=row.version,
            updated_at=row.updated_at,
            published_version=row.published_version,
            published_revision=row.published_revision,
            published_hash=row.published_hash,
        )

    async def lock_editor_draft(self, preset_id: UUID) -> EditorDraft | None:
        """Load the preset's draft locked for update within this transaction.

        All draft mutations lock first, so overlapping writers serialize
        on the row instead of racing past a detached version check.
        """
        row = (
            await self._session.execute(
                select(EditorDraftRow)
                .where(EditorDraftRow.preset_id == preset_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        return self._to_editor_draft(row) if row is not None else None

    async def get_editor_draft(self, preset_id: UUID) -> EditorDraft | None:
        """The one durable draft for a preset, if any."""
        row = (
            await self._session.execute(
                select(EditorDraftRow).where(EditorDraftRow.preset_id == preset_id)
            )
        ).scalar_one_or_none()
        return self._to_editor_draft(row) if row is not None else None

    async def add_editor_draft(self, draft: EditorDraft, created_at: datetime) -> None:
        try:
            self._session.add(
                EditorDraftRow(
                    id=draft.id,
                    preset_id=draft.preset_id,
                    base_revision=draft.base_revision,
                    fields=dict(draft.fields),
                    version=draft.version,
                    created_at=created_at,
                    updated_at=draft.updated_at,
                    published_version=draft.published_version,
                    published_revision=draft.published_revision,
                    published_hash=draft.published_hash,
                )
            )
            await self._session.flush()
        except SqlIntegrityError as exc:
            if unique_violation(exc, "uq_editor_draft_preset"):
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    f"duplicate editor draft for preset: {draft.preset_id}",
                ) from exc
            raise

    async def save_editor_draft(self, draft: EditorDraft, expected_version: int) -> EditorDraft:
        row = await self._session.get(
            EditorDraftRow, draft.id, with_for_update=True
        )
        if row is None:
            raise missing("editor draft", draft.id)
        if row.version != expected_version:
            raise version_conflict("editor draft", draft.id, expected_version, row.version)
        row.base_revision = draft.base_revision
        row.fields = dict(draft.fields)
        row.version = expected_version + 1
        row.updated_at = draft.updated_at
        row.published_version = draft.published_version
        row.published_revision = draft.published_revision
        row.published_hash = draft.published_hash
        await self._session.flush()
        return draft.model_copy(update={"version": expected_version + 1})

    async def record_publication(
        self,
        draft_id: EditorDraftId,
        expected_version: int,
        revision: int,
        content_hash: str,
        updated_at: datetime,
    ) -> None:
        """Stamp the publication receipt without consuming a draft version.

        The draft stays at its version so an identical retry still
        matches the receipt, and completion can verify no newer edits
        exist. Locked and version-checked like every other mutation.
        """
        row = await self._session.get(
            EditorDraftRow, draft_id, with_for_update=True
        )
        if row is None:
            raise missing("editor draft", draft_id)
        if row.version != expected_version:
            raise version_conflict("editor draft", draft_id, expected_version, row.version)
        row.published_version = expected_version
        row.published_revision = revision
        row.published_hash = content_hash
        row.updated_at = updated_at
        await self._session.flush()

    async def delete_editor_draft(self, draft_id: EditorDraftId, expected_version: int) -> None:
        row = await self._session.get(
            EditorDraftRow, draft_id, with_for_update=True
        )
        if row is None:
            raise missing("editor draft", draft_id)
        if row.version != expected_version:
            raise version_conflict("editor draft", draft_id, expected_version, row.version)
        await self._session.delete(row)
        await self._session.flush()

    def _to_publication(self, row: EditorPublicationRow) -> EditorPublication:
        return EditorPublication(
            draft_id=row.draft_id,
            preset_id=row.preset_id,
            draft_version=row.draft_version,
            revision=row.revision,
            content_hash=row.content_hash,
            created_at=row.created_at,
        )

    async def add_publication(self, receipt: EditorPublication) -> None:
        try:
            self._session.add(
                EditorPublicationRow(
                    draft_id=receipt.draft_id,
                    preset_id=receipt.preset_id,
                    draft_version=receipt.draft_version,
                    revision=receipt.revision,
                    content_hash=receipt.content_hash,
                    created_at=receipt.created_at,
                )
            )
            await self._session.flush()
        except SqlIntegrityError as exc:
            if unique_violation(exc, "pk_editor_publication"):
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    f"duplicate publication for draft {receipt.draft_id} "
                    f"version {receipt.draft_version}",
                ) from exc
            raise

    async def list_publications_for_draft(
        self, draft_id: EditorDraftId
    ) -> list[EditorPublication]:
        """Durable replay log: survives draft completion; explicit discard voids it."""
        query = (
            select(EditorPublicationRow)
            .where(EditorPublicationRow.draft_id == draft_id)
            .order_by(EditorPublicationRow.draft_version)
        )
        rows = (await self._session.execute(query)).scalars().all()
        return [self._to_publication(row) for row in rows]

    async def delete_publications_for_draft(self, draft_id: EditorDraftId) -> None:
        """Void every receipt for the draft: no version replays afterwards."""
        query = select(EditorPublicationRow).where(
            EditorPublicationRow.draft_id == draft_id
        )
        rows = (await self._session.execute(query)).scalars().all()
        for row in rows:
            await self._session.delete(row)
        if rows:
            await self._session.flush()

    def _to_creation_receipt(self, row: PresetCreationReceiptRow) -> PresetCreationReceipt:
        return PresetCreationReceipt(
            operator=row.operator,
            idempotency_key=row.idempotency_key,
            request_hash=row.request_hash,
            created_preset_id=row.created_preset_id,
            created_at=row.created_at,
        )

    async def put_creation_receipt(self, receipt: PresetCreationReceipt) -> None:
        self._session.add(
            PresetCreationReceiptRow(
                operator=receipt.operator,
                idempotency_key=receipt.idempotency_key,
                request_hash=receipt.request_hash,
                created_preset_id=receipt.created_preset_id,
                created_at=receipt.created_at,
            )
        )
        await self._session.flush()

    async def find_creation_receipt(
        self, operator: str, key: str
    ) -> PresetCreationReceipt | None:
        row = await self._session.get(PresetCreationReceiptRow, (operator, key))
        return self._to_creation_receipt(row) if row is not None else None

    async def latest_revision(self, preset_id: UUID) -> PresetRevision:
        query = (
            select(PresetRevisionRow)
            .where(PresetRevisionRow.preset_id == preset_id)
            .order_by(PresetRevisionRow.revision.desc())
            .limit(1)
        )
        row = (await self._session.execute(query)).scalars().first()
        if row is None:
            raise missing("preset revision", preset_id)
        return self._to_revision(row)
