"""Durable editor drafts for preset revisions (E3).

One partial draft per preset, guarded by optimistic versions. Every
mutation locks the draft row first, so overlapping writers serialize
on the row instead of racing past a detached version check. Draft
saves stay lenient so incomplete work survives; publishing merges the
draft over its base revision payload and validates the strict preset
schema, so fields the editor never shows are preserved verbatim.

Publication records a receipt per published draft version (draft
version, revision, content hash), so edits saved after publishing
publish as the next revision under their own receipt. An identical
publish retry replays the recorded revision — even after later
revisions exist, or while another draft occupies the preset — while
anything else stays a conflict.
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
    EditorPublication,
    PresetPayload,
    PresetRevision,
    canonical_payload_hash,
)
from worldsim.domain.time import utcnow

_adapter: TypeAdapter[PresetPayload] = TypeAdapter(PresetPayload)

_MAX_FIELDS = 64
_MAX_BYTES = 32 * 1024
_MAX_NAME = 128


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


def _check_name(name: Any) -> str | None:
    if name is None:
        return None
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= _MAX_NAME):
        raise DomainError(ErrorCode.VALIDATION_FAILED, "preset name must be 1..128 characters")
    return name.strip()


async def open_draft(
    factory: Callable[[], UnitOfWork], preset_id: UUID, base_revision: int
) -> tuple[EditorDraft, bool]:
    """Open the durable draft for a preset base revision.

    Reopening the same base replays the stored draft (second value True).
    A draft already open on another base must be discarded first: silently
    rebasing it could publish against the wrong content. Concurrent opens
    resolve the one-draft-per-preset constraint the same way.
    """
    try:
        async with factory() as uow:
            preset = await uow.presets.get_preset(preset_id)
            if preset.readonly:
                raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
            await uow.presets.get_revision(preset_id, base_revision)
            existing = await uow.presets.lock_editor_draft(preset_id)
            if existing is not None:
                if existing.base_revision != base_revision:
                    raise DomainError(
                        ErrorCode.PRECONDITION_FAILED,
                        f"draft already open on revision {existing.base_revision}; "
                        "discard it first",
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
    except DomainError as exc:
        if exc.code is not ErrorCode.IDEMPOTENCY_CONFLICT:
            raise
        # Lost an open race: adopt the winner's draft by the same rules.
        async with factory() as fresh:
            winner = await fresh.presets.get_editor_draft(preset_id)
        if winner is None or winner.base_revision != base_revision:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "a draft was opened concurrently on another revision; discard it first",
            ) from exc
        return winner, True


def _stale(kind: str, identity: UUID, expected: int, actual: int) -> DomainError:
    return DomainError(
        ErrorCode.VERSION_CONFLICT,
        f"stale {kind} {identity}: expected={expected} actual={actual}",
    )


async def save_draft(
    factory: Callable[[], UnitOfWork],
    preset_id: UUID,
    draft_id: UUID,
    expected_version: int,
    fields: Any,
) -> EditorDraft:
    """Persist partial editor fields in one locked transaction."""
    cleaned = _check_fields(fields)
    async with factory() as uow:
        draft = await uow.presets.lock_editor_draft(preset_id)
        if draft is None or draft.id != draft_id:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown editor draft: {draft_id}")
        if draft.version != expected_version:
            raise _stale("editor draft", draft_id, expected_version, draft.version)
        saved = await uow.presets.save_editor_draft(
            draft.model_copy(update={"fields": cleaned, "updated_at": utcnow()}),
            expected_version,
        )
        await uow.commit()
        return saved


async def discard_draft(
    factory: Callable[[], UnitOfWork], preset_id: UUID, draft_id: UUID, expected_version: int
) -> None:
    """Abandon a draft explicitly. Published revisions are never touched,
    but every publication receipt for the draft is voided with it: a
    later retry of a discarded request meets NOT_FOUND, not a replay."""
    async with factory() as uow:
        draft = await uow.presets.lock_editor_draft(preset_id)
        if draft is None or draft.id != draft_id:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown editor draft: {draft_id}")
        if draft.version != expected_version:
            raise _stale("editor draft", draft_id, expected_version, draft.version)
        await uow.presets.delete_publications_for_draft(draft_id)
        await uow.presets.delete_editor_draft(draft_id, expected_version)
        await uow.commit()


async def complete_draft(
    factory: Callable[[], UnitOfWork], preset_id: UUID, draft_id: UUID, expected_version: int
) -> None:
    """Retire a draft after its publication, deliberately.

    Succeeds only when the draft version still matches the published
    receipt: edits made after publishing are newer work that an
    explicit discard — not completion — must abandon. The durable
    receipt survives completion, so a late identical retry still
    replays its revision.
    """
    async with factory() as uow:
        draft = await uow.presets.lock_editor_draft(preset_id)
        if draft is None or draft.id != draft_id:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown editor draft: {draft_id}")
        if draft.version != expected_version:
            raise _stale("editor draft", draft_id, expected_version, draft.version)
        if (
            draft.published_version is None
            or draft.published_revision is None
            or draft.published_hash is None
            or draft.published_version != draft.version
        ):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "draft has unpublished changes; discard it explicitly",
            )
        await uow.presets.delete_editor_draft(draft_id, expected_version)
        await uow.commit()


async def _replay_from_log(
    uow: UnitOfWork, preset_id: UUID, draft_id: UUID, expected_version: int
) -> PresetRevision:
    """Replay the durable receipt for an identical retry.

    Matches on the exact draft and version — every successful save
    advances the version, so a matching version implies matching
    fields — and returns the original revision even when later
    revisions exist. A version this draft never published is a stale
    conflict; a draft that never published (or a receipt for another
    preset) is NOT_FOUND, never a guess.
    """
    receipts = [
        receipt
        for receipt in await uow.presets.list_publications_for_draft(draft_id)
        if receipt.preset_id == preset_id
    ]
    for receipt in receipts:
        if receipt.draft_version == expected_version:
            return await uow.presets.get_revision(receipt.preset_id, receipt.revision)
    if not receipts:
        raise DomainError(ErrorCode.NOT_FOUND, f"unknown editor draft: {draft_id}")
    latest = max(receipt.draft_version for receipt in receipts)
    raise DomainError(
        ErrorCode.VERSION_CONFLICT,
        f"stale editor draft {draft_id}: expected={expected_version} actual={latest}",
    )


async def publish_draft(
    factory: Callable[[], UnitOfWork],
    preset_id: UUID,
    draft_id: UUID,
    expected_version: int,
    preset_expected_version: int,
) -> PresetRevision:
    """Publish a draft as a new immutable revision, atomically.

    The draft merges over its base revision payload, so unexposed fields
    survive; the merged payload validates the strict preset schema, and
    a renamed draft updates the preset's display name in the same
    transaction while historical payloads keep theirs. The draft row
    lock serializes concurrent publishers; the preset version guards
    concurrent content. An identical retry — same draft and version —
    replays the recorded revision instead of conflicting or duplicating,
    even after later revisions exist, after the draft completed, or
    while another draft occupies the preset. Each published draft
    version keeps its own receipt, so edits saved after publishing
    publish as the next revision.
    """
    try:
        async with factory() as uow:
            draft = await uow.presets.lock_editor_draft(preset_id)
            if draft is None:
                # Late retry after completion: the draft is gone but the
                # durable receipt answers for it.
                return await _replay_from_log(uow, preset_id, draft_id, expected_version)
            if draft.id != draft_id:
                # Another draft occupies the preset. The requested draft
                # may still have a durable receipt: resolve it by the
                # same replay rules, without touching the live draft.
                return await _replay_from_log(uow, preset_id, draft_id, expected_version)
            if draft.version != expected_version:
                # Edited since without a matching receipt: a plain stale
                # conflict. A receipt decides identical replay, below.
                if not await uow.presets.list_publications_for_draft(draft_id):
                    raise _stale("editor draft", draft_id, expected_version, draft.version)
                return await _replay_from_log(uow, preset_id, draft_id, expected_version)
            preset = await uow.presets.get_preset(preset_id)
            if preset.readonly:
                raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
            base = await uow.presets.get_revision(preset_id, draft.base_revision)
            merged = base.payload.model_dump(mode="json")
            merged.update({k: v for k, v in draft.fields.items() if k != "kind"})
            merged["kind"] = preset.kind.value
            parsed = _parse_strict(preset.kind.value, merged)
            content_hash = canonical_payload_hash(parsed)
            # An identical retry that committed and lost its response
            # lands here with a receipt already recorded: replay it,
            # never duplicate — even when later revisions moved on. A
            # matching version implies matching fields (every save
            # advances the version), so the hash must agree too.
            prior = [
                receipt
                for receipt in await uow.presets.list_publications_for_draft(draft.id)
                if receipt.draft_version == expected_version
            ]
            if prior:
                if prior[0].content_hash != content_hash:
                    raise DomainError(
                        ErrorCode.VERSION_CONFLICT,
                        f"draft {draft.id} version {expected_version} "
                        "already published different content",
                    )
                return await uow.presets.get_revision(preset_id, prior[0].revision)
            if preset.version != preset_expected_version:
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT,
                    f"stale preset {preset_id}: expected={preset_expected_version} "
                    f"actual={preset.version}",
                )
            next_revision = preset.current_revision + 1
            now = utcnow()
            revision = PresetRevision(
                preset_id=preset_id,
                revision=next_revision,
                schema_version=1,
                payload=parsed,
                content_hash=content_hash,
                created_at=now,
            )
            await uow.presets.add_revision(revision)
            renamed = _check_name(draft.fields.get("name"))
            await uow.presets.save_preset(
                preset.model_copy(
                    update={
                        "current_revision": next_revision,
                        **({"name": renamed} if renamed is not None else {}),
                    }
                ),
                preset_expected_version,
            )
            await uow.presets.add_publication(
                EditorPublication(
                    draft_id=draft.id,
                    preset_id=preset_id,
                    draft_version=expected_version,
                    revision=next_revision,
                    content_hash=content_hash,
                    created_at=now,
                )
            )
            await uow.presets.record_publication(
                draft.id, expected_version, next_revision, content_hash, now
            )
            await uow.commit()
            return revision
    except DomainError as exc:
        if exc.code is not ErrorCode.IDEMPOTENCY_CONFLICT:
            raise
        # Lost a receipt race with a concurrent publisher of this same
        # draft: the failed session already rolled back on context exit.
        # Adopt the winner's receipt by the same replay rules.
        async with factory() as fresh:
            return await _replay_from_log(fresh, preset_id, draft_id, expected_version)
