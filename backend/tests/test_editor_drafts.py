"""Durable editor drafts for preset revisions (E3, review follow-up).

Draft saves stay lenient so incomplete work survives; publishing merges
the draft over its base revision and validates the strict preset
schema, preserving fields the editor never shows. Concurrency is
optimistic on both the draft and the preset; an ambiguous publish
retry adopts when the latest revision already carries the attempted
content, else it is a genuine conflict.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest
from pydantic import TypeAdapter

from worldsim.application import editor_drafts as service
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_preset_id
from worldsim.domain.presets import Preset, PresetKind, PresetPayload, PresetRevision
from worldsim.domain.time import utcnow
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

_adapter: TypeAdapter[PresetPayload] = TypeAdapter(PresetPayload)


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _factory() -> Any:
    engine = create_engine(Settings())
    return lambda: create_unit_of_work(engine)


def _world_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": "world",
        "name": "Vale",
        "description": "A valley.",
        "lore": "Old roads.",
        "locations": [{"key": "hearth", "name": "Hearth"}],
        "travel": [],
        "starting_location_key": "hearth",
        "default_cast": [],
    }
    payload.update(overrides)
    return payload


async def _make_preset(
    factory: Any, payload: dict[str, Any] | None = None, readonly: bool = False
) -> Preset:
    now = utcnow()
    preset = Preset(
        id=new_preset_id(), kind=PresetKind.WORLD, name="Vale", readonly=readonly, created_at=now
    )
    parsed = _adapter.validate_python(dict(payload or _world_payload()))
    assert parsed.kind == "world"
    async with factory() as uow:
        await uow.presets.add_preset(preset)
        await uow.presets.add_revision(
            PresetRevision(
                preset_id=preset.id,
                revision=1,
                schema_version=1,
                payload=parsed,
                content_hash="test-seed",
                created_at=now,
            )
        )
        await uow.commit()
    return preset


async def _fields(factory: Any, preset_id: UUID, draft_id: UUID) -> dict[str, Any]:
    async with factory() as uow:
        draft = await uow.presets.get_editor_draft(preset_id)
    assert draft is not None and draft.id == draft_id
    return dict(draft.fields)


def test_open_save_discard_roundtrip(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, replayed = await service.open_draft(factory, preset.id, 1)
        assert replayed is False
        assert draft.base_revision == 1 and draft.version == 1

        reopened, replayed = await service.open_draft(factory, preset.id, 1)
        assert replayed is True and reopened.id == draft.id

        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        assert saved.version == 2
        assert await _fields(factory, preset.id, draft.id) == {
            "description": "A greener valley."
        }

        await service.discard_draft(factory, preset.id, draft.id)
        async with factory() as uow:
            assert await uow.presets.get_editor_draft(preset.id) is None

    _run(_inner())


def test_open_conflicts_and_save_guards(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)

        with pytest.raises(DomainError) as exc:
            await service.open_draft(factory, preset.id, 2)
        assert exc.value.code is ErrorCode.NOT_FOUND

        with pytest.raises(DomainError) as exc:
            await service.save_draft(factory, preset.id, draft.id, 99, {"description": "x"})
        assert exc.value.code is ErrorCode.VERSION_CONFLICT

        with pytest.raises(DomainError) as exc:
            await service.save_draft(factory, preset.id, draft.id, 1, ["not", "an", "object"])
        assert exc.value.code is ErrorCode.VALIDATION_FAILED

        with pytest.raises(DomainError) as exc:
            await service.save_draft(factory, preset.id, draft.id, 1, {"x": "y" * (33 * 1024)})
        assert exc.value.code is ErrorCode.VALIDATION_FAILED

    _run(_inner())


def test_reopen_other_base_needs_discard_first(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        first, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(factory, preset.id, first.id, 1, {"description": "v2"})
        published = await service.publish_draft(factory, preset.id, first.id, saved.version, 0)
        assert published.revision == 2
        # The draft still pins revision 1: reopening revision 2 must not
        # silently rebase it.
        with pytest.raises(DomainError) as exc:
            await service.open_draft(factory, preset.id, 2)
        assert exc.value.code is ErrorCode.PRECONDITION_FAILED
        await service.discard_draft(factory, preset.id, first.id)
        second, replayed = await service.open_draft(factory, preset.id, 2)
        assert replayed is False and second.base_revision == 2

    _run(_inner())


def test_publish_merges_and_preserves_unexposed_fields(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        published = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert published.revision == 2
        body = published.payload.model_dump(mode="json")
        assert body["description"] == "A greener valley."
        # Never shown in the editor, never lost.
        assert body["lore"] == "Old roads."
        assert body["locations"] == [{"key": "hearth", "name": "Hearth", "description": None}]
        async with factory() as uow:
            current = await uow.presets.get_preset(preset.id)
            assert current.current_revision == 2
            first = await uow.presets.get_revision(preset.id, 1)
            assert first.payload.model_dump(mode="json")["description"] == "A valley."

    _run(_inner())


def test_publish_rejects_invalid_merged_payload(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        # An incomplete save is fine...
        saved = await service.save_draft(factory, preset.id, draft.id, 1, {"locations": []})
        assert saved.version == 2
        # ...but publishing validates strictly.
        with pytest.raises(DomainError) as exc:
            await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert exc.value.code is ErrorCode.VALIDATION_FAILED
        async with factory() as uow:
            assert (await uow.presets.get_preset(preset.id)).current_revision == 1

    _run(_inner())


def test_readonly_presets_reject_drafts(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory, readonly=True)
        with pytest.raises(DomainError) as exc:
            await service.open_draft(factory, preset.id, 1)
        assert exc.value.code is ErrorCode.FORBIDDEN

    _run(_inner())


def test_ambiguous_publish_retry_adopts_on_matching_hash(migrated_db: None) -> None:
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        first = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        # The response never arrived: retrying with the same stale versions
        # conflicts, and the latest revision already carries our content.
        with pytest.raises(DomainError) as exc:
            await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert exc.value.code is ErrorCode.VERSION_CONFLICT
        async with factory() as uow:
            latest = await uow.presets.latest_revision(preset.id)
            assert latest.revision == 2
            assert latest.content_hash == first.content_hash

        # A genuine rival publication is distinguishable: different hash.
        await service.discard_draft(factory, preset.id, draft.id)
        rival, _ = await service.open_draft(factory, preset.id, 1)
        rival_saved = await service.save_draft(
            factory, preset.id, rival.id, 1, {"description": "A drier valley."}
        )
        with pytest.raises(DomainError) as exc:
            await service.publish_draft(factory, preset.id, rival.id, rival_saved.version, 0)
        assert exc.value.code is ErrorCode.VERSION_CONFLICT
        async with factory() as uow:
            latest = await uow.presets.latest_revision(preset.id)
            assert latest.content_hash == first.content_hash

    _run(_inner())


def test_missing_preset_and_draft(migrated_db: None) -> None:
    async def _inner() -> None:
        from uuid import uuid4

        factory = _factory()
        with pytest.raises(DomainError) as exc:
            await service.open_draft(factory, uuid4(), 1)
        assert exc.value.code is ErrorCode.NOT_FOUND
        preset = await _make_preset(factory)
        with pytest.raises(DomainError) as exc:
            await service.save_draft(factory, preset.id, uuid4(), 1, {})
        assert exc.value.code is ErrorCode.NOT_FOUND

    _run(_inner())
