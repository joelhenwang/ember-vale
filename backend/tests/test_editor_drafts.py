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

        with pytest.raises(DomainError) as exc:
            await service.discard_draft(factory, preset.id, draft.id, 99)
        assert exc.value.code is ErrorCode.VERSION_CONFLICT
        await service.discard_draft(factory, preset.id, draft.id, saved.version)
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
        await service.discard_draft(factory, preset.id, first.id, saved.version)
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


def test_identical_publish_retry_replays_original_revision(migrated_db: None) -> None:
    """An ambiguous retry returns the recorded revision, never a duplicate."""
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        first = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert first.revision == 2
        # The response never arrived: the identical retry replays revision
        # 2 instead of conflicting or duplicating.
        replayed = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert replayed.revision == 2
        assert replayed.content_hash == first.content_hash
        async with factory() as uow:
            latest = await uow.presets.latest_revision(preset.id)
            assert latest.revision == 2

        # A different request against the same versions stays a conflict.
        await service.discard_draft(factory, preset.id, draft.id, saved.version)
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


def test_publish_replay_survives_later_revisions(migrated_db: None) -> None:
    """Replay returns the original revision even after rev 3 exists."""
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        first = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert first.revision == 2

        # A later revision lands through a fresh draft on base 2.
        await service.complete_draft(factory, preset.id, draft.id, saved.version)
        second_draft, _ = await service.open_draft(factory, preset.id, 2)
        second_saved = await service.save_draft(
            factory, preset.id, second_draft.id, 1, {"description": "A golden valley."}
        )
        third = await service.publish_draft(
            factory, preset.id, second_draft.id, second_saved.version, 1
        )
        assert third.revision == 3
        await service.complete_draft(factory, preset.id, second_draft.id, second_saved.version)

        # The late identical retry of the first publication still replays
        # revision 2 — from the durable log, after completion, with a
        # stale preset version and a newer revision in place.
        replayed = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert replayed.revision == 2
        assert replayed.content_hash == first.content_hash
        async with factory() as uow:
            assert (await uow.presets.get_preset(preset.id)).current_revision == 3

    _run(_inner())


def test_publish_rename_updates_display_name(migrated_db: None) -> None:
    """Rename, publish, reload: Library and studios see the new name."""
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"name": "Greener Vale"}
        )
        published = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert published.revision == 2
        async with factory() as uow:
            current = await uow.presets.get_preset(preset.id)
            assert current.name == "Greener Vale"
            first = await uow.presets.get_revision(preset.id, 1)
            assert first.payload.model_dump(mode="json")["name"] == "Vale"

        # Lenient save accepts the blank name; strict publish rejects it.
        blank = await service.save_draft(
            factory, preset.id, draft.id, saved.version, {"name": "  "}
        )
        with pytest.raises(DomainError) as exc:
            await service.publish_draft(factory, preset.id, draft.id, blank.version, 1)
        assert exc.value.code is ErrorCode.VALIDATION_FAILED

    _run(_inner())


def test_completed_draft_lifecycle(migrated_db: None) -> None:
    """Completion retires a published draft but never newer edits."""
    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        # Nothing published yet: completion refuses, discard stays explicit.
        with pytest.raises(DomainError) as exc:
            await service.complete_draft(factory, preset.id, draft.id, saved.version)
        assert exc.value.code is ErrorCode.PRECONDITION_FAILED

        published = await service.publish_draft(factory, preset.id, draft.id, saved.version, 0)
        assert published.revision == 2
        await service.complete_draft(factory, preset.id, draft.id, saved.version)
        async with factory() as uow:
            assert await uow.presets.get_editor_draft(preset.id) is None

        # Edits after publishing block completion: they are newer work.
        third, _ = await service.open_draft(factory, preset.id, 2)
        third_saved = await service.save_draft(
            factory, preset.id, third.id, 1, {"description": "A golden valley."}
        )
        await service.publish_draft(factory, preset.id, third.id, third_saved.version, 1)
        fourth_saved = await service.save_draft(
            factory, preset.id, third.id, third_saved.version, {"description": "A blue valley."}
        )
        with pytest.raises(DomainError) as exc:
            await service.complete_draft(factory, preset.id, third.id, fourth_saved.version)
        assert exc.value.code is ErrorCode.PRECONDITION_FAILED

    _run(_inner())


def test_overlapping_saves_serialize_on_the_row(
    migrated_db: None, monkeypatch: Any
) -> None:
    """Two saves inside the window together: one wins, one conflicts."""
    from worldsim.infrastructure.repositories.presets import SqlAlchemyPresetRepository

    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        entered_a = asyncio.Event()
        entered_b = asyncio.Event()
        calls: list[str] = []
        original = SqlAlchemyPresetRepository.lock_editor_draft

        # The gate sits ahead of the row lock: both appliers must be
        # inside before either can serialize on the row. (Gating behind
        # the lock would deadlock the second waiter against the first.)
        async def gated(self: Any, preset_id: UUID) -> Any:
            calls.append("in")
            (entered_a if len(calls) == 1 else entered_b).set()
            await asyncio.gather(entered_a.wait(), entered_b.wait())
            return await original(self, preset_id)

        monkeypatch.setattr(SqlAlchemyPresetRepository, "lock_editor_draft", gated)
        outcomes = await asyncio.gather(
            service.save_draft(factory, preset.id, draft.id, 1, {"description": "A wins."}),
            service.save_draft(factory, preset.id, draft.id, 1, {"description": "B wins."}),
            return_exceptions=True,
        )
        assert calls == ["in", "in"]
        wins = [o for o in outcomes if not isinstance(o, BaseException)]
        losses = [o for o in outcomes if isinstance(o, DomainError)]
        assert len(wins) == 1 and len(losses) == 1
        assert losses[0].code is ErrorCode.VERSION_CONFLICT
        assert await _fields(factory, preset.id, draft.id) in (
            {"description": "A wins."},
            {"description": "B wins."},
        )

    _run(_inner())


def test_overlapping_publishes_converge_on_one_revision(
    migrated_db: None, monkeypatch: Any
) -> None:
    """Two publishes inside the window together persist one revision."""
    from worldsim.infrastructure.repositories.presets import SqlAlchemyPresetRepository

    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        draft, _ = await service.open_draft(factory, preset.id, 1)
        saved = await service.save_draft(
            factory, preset.id, draft.id, 1, {"description": "A greener valley."}
        )
        entered_a = asyncio.Event()
        entered_b = asyncio.Event()
        calls: list[str] = []
        original = SqlAlchemyPresetRepository.lock_editor_draft

        async def gated(self: Any, preset_id: UUID) -> Any:
            calls.append("in")
            (entered_a if len(calls) == 1 else entered_b).set()
            await asyncio.gather(entered_a.wait(), entered_b.wait())
            return await original(self, preset_id)

        monkeypatch.setattr(SqlAlchemyPresetRepository, "lock_editor_draft", gated)
        first, second = await asyncio.gather(
            service.publish_draft(factory, preset.id, draft.id, saved.version, 0),
            service.publish_draft(factory, preset.id, draft.id, saved.version, 0),
        )
        assert calls == ["in", "in"]
        assert first.revision == second.revision == 2
        assert first.content_hash == second.content_hash
        async with factory() as uow:
            assert (await uow.presets.get_preset(preset.id)).current_revision == 2

    _run(_inner())


def test_overlapping_opens_resolve_to_one_draft(
    migrated_db: None, monkeypatch: Any
) -> None:
    """Two opens inside the window together share a single draft."""
    from worldsim.infrastructure.repositories.presets import SqlAlchemyPresetRepository

    async def _inner() -> None:
        factory = _factory()
        preset = await _make_preset(factory)
        entered_a = asyncio.Event()
        entered_b = asyncio.Event()
        calls: list[str] = []
        original = SqlAlchemyPresetRepository.add_editor_draft

        async def gated(self: Any, incoming: Any, created_at: Any) -> Any:
            calls.append("in")
            (entered_a if len(calls) == 1 else entered_b).set()
            await asyncio.gather(entered_a.wait(), entered_b.wait())
            return await original(self, incoming, created_at)

        monkeypatch.setattr(SqlAlchemyPresetRepository, "add_editor_draft", gated)
        (left, left_replayed), (right, right_replayed) = await asyncio.gather(
            service.open_draft(factory, preset.id, 1),
            service.open_draft(factory, preset.id, 1),
        )
        assert calls == ["in", "in"]
        assert left.id == right.id
        assert sorted([left_replayed, right_replayed]) == [False, True]

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
