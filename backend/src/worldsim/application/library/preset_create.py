"""Idempotent first publication of new presets (E3).

A stable client key plus the exact creation request replays the same
preset; the same key with different content conflicts instead. The
receipt, the preset, and its first revision commit atomically in one
transaction, so a lost response can be retried safely and simultaneous
submissions still mint exactly one preset.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_preset_id
from worldsim.domain.presets import (
    Preset,
    PresetCreationReceipt,
    PresetKind,
    PresetPayload,
    PresetRevision,
    canonical_payload_hash,
)
from worldsim.domain.time import utcnow

OPERATOR = "local"

_adapter: TypeAdapter[PresetPayload] = TypeAdapter(PresetPayload)


def request_hash(kind: str, name: str, payload: dict[str, Any]) -> str:
    """Canonical identity of a creation request: key order never matters."""
    canonical = json.dumps({"kind": kind, "name": name, "payload": payload}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _parse_strict(kind: str, payload: dict[str, Any]) -> PresetPayload:
    try:
        parsed = _adapter.validate_python(dict(payload, kind=kind))
    except Exception as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid preset: {exc}") from exc
    if parsed.kind != kind:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "payload kind mismatch")
    return parsed


async def create_preset(
    factory: Callable[[], UnitOfWork],
    kind: str,
    name: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> UUID:
    """Create a preset as revision 1, idempotently under a client key.

    The key is required: without a durable client identity a lost
    response and retry could mint two presets, so keyless creation stays
    on the legacy route path instead of here.
    """
    try:
        preset_kind = PresetKind(kind)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown kind: {kind}") from exc
    parsed = _parse_strict(preset_kind.value, payload)
    trimmed = name.strip() if isinstance(name, str) else ""
    if not (1 <= len(trimmed) <= 128):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, "preset name must be 1..128 characters"
        )
    key = idempotency_key.strip() if isinstance(idempotency_key, str) else ""
    if not key:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "idempotency key is required")
    wanted = request_hash(
        preset_kind.value, trimmed, parsed.model_dump(mode="json")
    )
    async with factory() as uow:
        existing = await uow.presets.find_creation_receipt(OPERATOR, key)
        if existing is not None:
            if existing.request_hash != wanted:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "idempotency key was used for a different request",
                )
            return existing.created_preset_id
        now = utcnow()
        preset = Preset(
            id=new_preset_id(),
            kind=preset_kind,
            name=trimmed,
            created_at=now,
        )
        revision = PresetRevision(
            preset_id=preset.id,
            revision=1,
            schema_version=1,
            payload=parsed,
            content_hash=canonical_payload_hash(parsed),
            created_at=now,
        )
        try:
            await uow.presets.add_preset(preset)
            await uow.presets.add_revision(revision)
            await uow.presets.put_creation_receipt(
                PresetCreationReceipt(
                    operator=OPERATOR,
                    idempotency_key=key,
                    request_hash=wanted,
                    created_preset_id=preset.id,
                    created_at=now,
                )
            )
            await uow.commit()
        except IntegrityError:
            # Lost a receipt race with a simultaneous submission of this
            # same key: this session rolled back, so adopt the winner.
            await uow.rollback()
            return await _replay_after_race(factory, key, wanted)
        return preset.id


async def _replay_after_race(
    factory: Callable[[], UnitOfWork], key: str, wanted: str
) -> UUID:
    """Adopt the winner's receipt by the same replay rules."""
    async with factory() as uow:
        existing = await uow.presets.find_creation_receipt(OPERATOR, key)
        if existing is None:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, "creation raced and left nothing"
            )
        if existing.request_hash != wanted:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "idempotency key was used for a different request",
            )
        return existing.created_preset_id
