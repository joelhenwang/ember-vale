"""Durable editor drafts for preset revisions (E3).

One partial draft per preset, guarded by optimistic versions. Draft
saves stay lenient so incomplete work survives; publishing merges the
draft over its base revision payload and validates the strict preset
schema, so fields the editor never shows are preserved verbatim.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from pydantic import TypeAdapter

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_editor_draft_id
from worldsim.domain.presets import (
    EditorDraft,
    PresetPayload,
    PresetRevision,
    canonical_payload_hash,
)
from worldsim.domain.time import utcnow

_adapter: TypeAdapter[PresetPayload] = TypeAdapter(PresetPayload)

_MAX_FIELDS = 64
_MAX_BYTES = 32 * 1024


def _check_fields(fields: Any) -> dict[str, Any]:
    """Lenient draft shape: a small JSON object, nothing more."""
    if not isinstance(fields, dict):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "draft fields must be an object")
    cleaned: dict[str, Any] = {}
    for key, value in cast(dict[Any, Any], fields).items():
        if not isinstance(key, str) or not (1 <= len(key) <= 128):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, "draft field names must be short strings"
            )
        cleaned[key] = value
    if len(cleaned) > _MAX_FIELDS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "draft carries too many fields")
    try:
        raw = json.dumps(cleaned)
    except (TypeError, ValueError) as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "draft fields must be JSON") from exc
    if len(raw.encode()) > _MAX_BYTES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "draft is too large")
    return cleaned


def _parse_strict(kind: str, payload: dict[str, Any]) -> PresetPayload:
    try:
        parsed = _adapter.validate_python(dict(payload, kind=kind))
    except Exception as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid preset: {exc}") from exc
    if parsed.kind != kind:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "payload kind mismatch")
    return parsed


async def open_draft(
    factory: Callable[[], UnitOfWork], preset_id: UUID, base_revision: int
) -> tuple[EditorDraft, bool]:
    """Open the durable draft for a preset base revision.

    Reopening the same base replays the stored draft (second value True).
    A draft already open on another base must be discarded first: silently
    rebasing it could publish against the wrong content.
    """
    async with factory() as uow:
        preset = await uow.presets.get_preset(preset_id)
        if preset.readonly:
            raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
        await uow.presets.get_revision(preset_id, base_revision)
        existing = await uow.presets.get_editor_draft(preset_id)
        if existing is not None:
            if existing.base_revision != base_revision:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    f"draft already open on revision {existing.base_revision}; discard it first",
                )
            return existing, True
        now = utcnow()
        draft = EditorDraft(
            id=new_editor_draft_id(),
            preset_id=preset_id,
            base_revision=base_revision,
            fields={},
            updated_at=now,
        )
        await uow.presets.add_editor_draft(draft, now)
        await uow.commit()
        return draft, False


async def _owned(factory: Callable[[], UnitOfWork], preset_id: UUID, draft_id: UUID) -> EditorDraft:
    async with factory() as uow:
        draft = await uow.presets.get_editor_draft(preset_id)
    if draft is None or draft.id != draft_id:
        raise DomainError(ErrorCode.NOT_FOUND, f"unknown editor draft: {draft_id}")
    return draft


async def save_draft(
    factory: Callable[[], UnitOfWork],
    preset_id: UUID,
    draft_id: UUID,
    expected_version: int,
    fields: Any,
) -> EditorDraft:
    """Persist partial editor fields; incomplete work is accepted."""
    draft = await _owned(factory, preset_id, draft_id)
    if draft.version != expected_version:
        raise DomainError(
            ErrorCode.VERSION_CONFLICT,
            f"stale editor draft {draft_id}: expected={expected_version} actual={draft.version}",
        )
    cleaned = _check_fields(fields)
    async with factory() as uow:
        saved = await uow.presets.save_editor_draft(
            draft.model_copy(update={"fields": cleaned, "updated_at": utcnow()}),
            expected_version,
        )
        await uow.commit()
        return saved


async def discard_draft(factory: Callable[[], UnitOfWork], preset_id: UUID, draft_id: UUID) -> None:
    """Abandon a draft. Published revisions are never touched."""
    await _owned(factory, preset_id, draft_id)
    async with factory() as uow:
        await uow.presets.delete_editor_draft(draft_id)
        await uow.commit()


async def publish_draft(
    factory: Callable[[], UnitOfWork],
    preset_id: UUID,
    draft_id: UUID,
    expected_version: int,
    preset_expected_version: int,
) -> PresetRevision:
    """Publish a draft as a new immutable revision.

    The draft merges over its base revision payload, so unexposed fields
    survive; the merged payload validates the strict preset schema. The
    preset version guards concurrent publishers. An ambiguous retry that
    meets VERSION_CONFLICT adopts when the latest revision already
    carries the attempted content hash, else it is a genuine conflict.
    """
    draft = await _owned(factory, preset_id, draft_id)
    if draft.version != expected_version:
        raise DomainError(
            ErrorCode.VERSION_CONFLICT,
            f"stale editor draft {draft_id}: expected={expected_version} actual={draft.version}",
        )
    async with factory() as uow:
        preset = await uow.presets.get_preset(preset_id)
        if preset.readonly:
            raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
        base = await uow.presets.get_revision(preset_id, draft.base_revision)
        merged = base.payload.model_dump(mode="json")
        merged.update({k: v for k, v in draft.fields.items() if k != "kind"})
        merged["kind"] = preset.kind.value
        parsed = _parse_strict(preset.kind.value, merged)
        next_revision = preset.current_revision + 1
        revision = PresetRevision(
            preset_id=preset_id,
            revision=next_revision,
            schema_version=1,
            payload=parsed,
            content_hash=canonical_payload_hash(parsed),
            created_at=utcnow(),
        )
        await uow.presets.add_revision(revision)
        await uow.presets.save_preset(
            preset.model_copy(update={"current_revision": next_revision}),
            preset_expected_version,
        )
        await uow.commit()
        return revision
