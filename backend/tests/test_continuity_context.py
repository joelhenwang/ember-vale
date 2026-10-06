"""Characters remember replies, in order, with when they happened."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.context.assembler import assemble
from worldsim.application.orchestration.stage1 import (
    SealedPhase,
    Stage1Orchestrator,
    director_summary,
)
from worldsim.application.ports.model_gateway import CompletionRequest
from worldsim.domain.characters import Character
from worldsim.domain.commands import CommunicateAction, MoveAction, WaitAction
from worldsim.domain.context import ContextRequest, SourceCandidate
from worldsim.domain.enums import ParticipantRole, Visibility
from worldsim.domain.intentions import card_drives, extract_intention
from worldsim.domain.narrative import NarrativeHook
from worldsim.domain.scenes import Intent, Reaction, Scene, SceneParticipant
from worldsim.domain.time import phase_label
from worldsim.domain.world import Location
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def test_phase_label() -> None:
    assert phase_label(0) == "Day 1, dawn"
    assert phase_label(3) == "Day 1, noon"
    assert phase_label(13) == "Day 2, noon"


def _candidate(source: str, index: int, score: float, ordinal: int = 0) -> SourceCandidate:
    return SourceCandidate(
        source_id=source,
        data_class="observations",
        visibility=Visibility.PUBLIC,
        text=f"{source} at {index}",
        score=score,
        created_phase_index=index,
        ordinal=ordinal,
    )


def _request() -> ContextRequest:
    return ContextRequest(
        role="character_decision",
        actor_id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        phase_run_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        purpose="decide",
    )


def test_observations_render_oldest_first_attempt_before_reply() -> None:
    # Newer observations score higher (decay), so ranking alone shows them
    # newest first, and same-phase ties fall to random source ids.
    candidates = [
        _candidate("obs:z-reply", 2, 0.9, ordinal=1),
        _candidate("obs:a-early", 1, 0.5),
        _candidate("obs:y-attempt", 2, 0.9, ordinal=0),
    ]
    envelope, _included, _excluded = assemble(_request(), candidates)
    section = next(s for s in envelope.sections if s.name == "observations")
    order = [e.split(">>", 1)[1].split(" at")[0] for e in section.entries]
    assert order == ["obs:a-early", "obs:y-attempt", "obs:z-reply"]


def test_budget_still_keeps_the_most_salient() -> None:
    request = _request().model_copy(update={"section_budgets": {"observations": 140}})
    candidates = [_candidate(f"obs:{i}", i, score=i / 10) for i in range(1, 6)]
    envelope, included, excluded = assemble(request, candidates)
    kept = {x.source_id for x in included if x.kind == "observations"}
    assert "obs:5" in kept and "obs:4" in kept  # newest survive the budget
    assert any(x.source_id == "obs:1" for x in excluded)
    section = next(s for s in envelope.sections if s.name == "observations")
    rendered = " ".join(section.entries)
    assert rendered.index("obs:4 at") < rendered.index("obs:5 at")  # still chronological


def _perceive(
    reactions: Callable[[dict[str, uuid.UUID]], list[Reaction]],
) -> tuple[list[Any], list[Any], dict[str, uuid.UUID]]:
    ids = {k: uuid.uuid4() for k in ("world", "run", "snapshot", "scene", "hearth", "wren", "ash")}
    intent = Intent(
        id=uuid.uuid4(),
        world_id=ids["world"],
        snapshot_id=ids["snapshot"],
        phase_run_id=ids["run"],
        author_character_id=ids["wren"],
        action=CommunicateAction(
            character_id=ids["wren"],
            snapshot_id=ids["snapshot"],
            target_character_id=ids["ash"],
            topic="What brings you here?",
        ),
        idempotency_key="t",
    )
    scene = Scene(
        id=ids["scene"],
        world_id=ids["world"],
        phase_run_id=ids["run"],
        snapshot_id=ids["snapshot"],
        participants=[
            SceneParticipant(character_id=ids["wren"], role=ParticipantRole.INITIATOR),
            SceneParticipant(character_id=ids["ash"], role=ParticipantRole.REACTOR),
        ],
        intent_ids=[intent.id],
    )
    sealed = SealedPhase(
        snapshot_id=ids["snapshot"],
        versions={},
        locations={ids["wren"]: ids["hearth"], ids["ash"]: ids["hearth"]},
    )
    names = {ids["wren"]: "Wren", ids["ash"]: "Ash"}
    perceive = Stage1Orchestrator._perceive_scene  # pyright: ignore[reportPrivateUsage]
    specs, memories = perceive(
        cast(Any, None), ids["world"], sealed, scene, [intent], names, reactions(ids)
    )
    return specs, memories, ids


def _reply(ids: dict[str, uuid.UUID], action: Any) -> Reaction:
    return Reaction(
        id=uuid.uuid4(),
        world_id=ids["world"],
        attempt_id=uuid.uuid4(),
        scene_id=ids["scene"],
        reactor_character_id=ids["ash"],
        action=action,
    )


def test_spoken_reply_is_remembered_by_both() -> None:
    def reactions(ids: dict[str, uuid.UUID]) -> list[Reaction]:
        return [
            _reply(
                ids,
                CommunicateAction(
                    character_id=ids["ash"],
                    snapshot_id=ids["snapshot"],
                    target_character_id=ids["wren"],
                    topic='"Just passing through."',
                ),
            )
        ]

    specs, memories, ids = _perceive(reactions)
    replies = {
        spec.observer_id: fact.value
        for spec in specs
        for fact in spec.facts
        if fact.key == "reply:communicate"
    }
    assert replies == {
        ids["wren"]: 'Ash replies to Wren: "Just passing through."',
        ids["ash"]: 'Ash replies to Wren: "Just passing through."',
    }
    # Each memory points at the owner's own attempt when they made one.
    wren_memory = next(m for m in memories if m.owner_id == ids["wren"])
    assert wren_memory.observation_index is not None
    pointed = specs[wren_memory.observation_index]
    assert pointed.observer_id == ids["wren"] and pointed.facts[0].key == "attempt:communicate"


def test_silent_replies_are_not_stored() -> None:
    def reactions(ids: dict[str, uuid.UUID]) -> list[Reaction]:
        return [_reply(ids, WaitAction(character_id=ids["ash"], snapshot_id=ids["snapshot"]))]

    specs, _memories, _ids = _perceive(reactions)
    assert not [f for s in specs for f in s.facts if f.key.startswith("reply:")]


def test_extract_intention_and_card_drives() -> None:
    stated = json.dumps({"family": "wait", "intention": "  walk to the\nmarket "})
    assert extract_intention(stated) == "walk to the market"
    assert extract_intention('{"family": "wait"}') is None
    assert extract_intention('{"intention": 3}') is None
    assert extract_intention("{oops") is None
    assert extract_intention(None) is None
    drives = card_drives("Patient.\nWants: a quiet stall\nAvoids: crowds\nWants:\nStyles: dry")
    assert drives == ["Wants: a quiet stall", "Avoids: crowds"]


@pytest.fixture
def stage1_client(migrated_db: None) -> Iterator[tuple[ApiClient, FakeGateway]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway


def test_stated_intention_reaches_the_next_decision(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        text = base(request)
        if (
            "You decide" in (request.system or "")
            and "<<untrusted:identity>>Wren" in request.prompt
        ):
            return json.dumps(
                {**json.loads(text or "{}"), "family": "wait", "intention": "walk to the market"}
            )
        return text

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    before = len(gateway.sent_requests)
    assert _advance(client, ids["world"], 2).status_code == 200

    wren_prompts = [
        r.prompt
        for r in gateway.sent_requests[before:]
        if "You decide" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    ]
    assert wren_prompts
    assert "Your current intention (since Day 1, sunrise): walk to the market" in wren_prompts[0]
    assert "now Day 1, morning" in wren_prompts[0]


def test_narrator_is_told_where_the_scene_happens(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        # Observing (not waiting) keeps the phase from being quiet, so the
        # narrator model is actually asked.
        if "You decide" in (request.system or ""):
            return json.dumps({"family": "observe", "focus": "the room"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    narrator = [r.prompt for r in gateway.sent_requests if "You narrate" in (r.system or "")]
    assert any("The scene takes place at Hearth." in p for p in narrator)
    assert any("The scene takes place at Market." in p for p in narrator)


def test_director_summary_lists_ids_places_and_stalls() -> None:
    world = uuid.uuid4()
    hearth = Location(id=uuid.uuid4(), world_id=world, name="Hearth")
    wren = Character(
        id=uuid.uuid4(),
        world_id=world,
        name="Wren",
        card_version=1,
        location_id=hearth.id,
        stamina=80,
        mana=40,
    )
    summary = director_summary(
        12, [wren], [hearth], [], [], ["Day 2, dawn: Wren waits."], quiet_streak=3
    )
    assert f"Wren (id {wren.id}, at Hearth)" in summary
    assert f"Hearth (id {hearth.id})" in summary
    assert "- Day 2, dawn: Wren waits." in summary
    assert "Idle beats in a row: 3" in summary
    assert summary.startswith("Phase 12 (Day 2, morning).")


def test_open_hooks_reach_characters_as_local_talk(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())

    async def add_hooks() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                for title, who in (("A stranger at the market", []), ("Ash's debt", [ids["ash"]])):
                    await uow.narrative.add_hook(
                        NarrativeHook(
                            id=uuid.uuid4(),
                            world_id=ids["world"],
                            title=title,
                            purpose="Someone is asking questions.",
                            participant_ids=who,
                        )
                    )
                await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(add_hooks())
    gateway.route = _route_for(ids, {})
    assert _advance(client, ids["world"], 1).status_code == 200
    wren = next(
        r.prompt
        for r in gateway.sent_requests
        if "You decide" in (r.system or "") and "<<untrusted:identity>>Wren" in r.prompt
    )
    assert "Word around the vale: A stranger at the market." in wren
    assert "Ash's debt" not in wren  # a hook for Ash only


def test_moves_are_remembered_with_their_destination() -> None:
    from worldsim.application.orchestration import stage1

    wren, market, snap = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    move = MoveAction(character_id=wren, snapshot_id=snap, destination_location_id=market)
    summarize = stage1._summarize  # pyright: ignore[reportPrivateUsage]
    assert summarize(move, {wren: "Wren", market: "Market"}) == "Wren goes to Market"
    assert summarize(move, {wren: "Wren"}) == "Wren goes to another place"


def test_director_sees_each_characters_intention() -> None:
    world = uuid.uuid4()
    hearth = Location(id=uuid.uuid4(), world_id=world, name="Hearth")
    ash = Character(
        id=uuid.uuid4(),
        world_id=world,
        name="Ash",
        card_version=1,
        location_id=hearth.id,
        stamina=80,
        mana=40,
    )
    summary = director_summary(
        5, [ash], [hearth], [], [], [], 3, {ash.id: "wait for Bramble to come back"}
    )
    assert f"Ash (id {ash.id}, at Hearth, intends: wait for Bramble to come back)" in summary


def test_scenes_where_everyone_waits_are_marked_idle(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    gateway.route = _route_for(ids, {})  # both characters wait
    assert _advance(client, ids["world"], 1).status_code == 200
    feed = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(ids["world"]), "after": 0, "limit": 50},
        headers={"X-Worldsim-Role": "watcher"},
    ).json()["entries"]
    scenes = [e for e in feed if e["event_type"] == "action_resolved"]
    assert scenes and all(e["idle"] for e in scenes)


def test_streak_counts_the_most_recent_run() -> None:
    from worldsim.application.orchestration import stage1

    streak = stage1._streak  # pyright: ignore[reportPrivateUsage]
    assert streak({1: True, 2: False, 3: True, 4: True}) == 2
    assert streak({1: True, 2: True, 3: False}) == 0
    assert streak({}) == 0


def test_director_is_told_when_only_talk_happens(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        system = request.system or ""
        if "You direct" in system:
            return json.dumps({"action": "noop", "reason": "watching"})
        if "You decide" in system:
            wren = "<<untrusted:identity>>Wren" in request.prompt
            target = ids["ash"] if wren else ids["wren"]
            return json.dumps(
                {"family": "communicate", "target_character_id": str(target), "topic": "the tale"}
            )
        return base(request)

    gateway.route = route
    for index in range(1, 5):  # director runs at beats 1 and 4 (cooldown 3)
        assert _advance(client, ids["world"], index).status_code == 200
    director = [r.prompt for r in gateway.sent_requests if "You direct" in (r.system or "")]
    assert "Talk-only beats in a row: 3" in director[-1]


def test_long_lines_are_clipped_to_fit_an_observation() -> None:
    from worldsim.application.orchestration import stage1

    clip = stage1._clip  # pyright: ignore[reportPrivateUsage]
    assert clip("short") == "short"
    long = "x" * 700
    assert len(clip(long)) == 512 and clip(long).endswith("…")


def test_recap_is_labelled_rejected_alone_and_never_a_fallback_beat() -> None:
    from worldsim.application.graphs.narrate import (
        RECAP_FACT_KEY,
        _render_fact_line,  # pyright: ignore[reportPrivateUsage]
        beats_valid,
        fallback_beats,
    )
    from worldsim.domain.enums import NarrationKind
    from worldsim.domain.narration import BeatProposal

    recap = {"key": RECAP_FACT_KEY, "value": "Day 1, dawn: Wren tried the crate."}
    assert "[recap — already seen; continuity only]" in _render_fact_line(recap)

    def beat(*keys: str) -> BeatProposal:
        return BeatProposal(
            kind=NarrationKind.NARRATION, text="Again at the crate.", cited_fact_keys=list(keys)
        )

    visible = frozenset({RECAP_FACT_KEY, "attempt:interact"})

    def check(*keys: str) -> str | None:
        return beats_valid(
            [beat(*keys)], visible_keys=visible, audience_ids=frozenset(), beats_budget=3
        )

    assert check(RECAP_FACT_KEY) is not None
    assert check(RECAP_FACT_KEY, "attempt:interact") is None

    beats = fallback_beats(
        world_id=uuid.uuid4(),
        scene_id=None,
        event_id=uuid.uuid4(),
        visible_facts=[recap, {"key": "attempt:interact", "value": "Wren lifts the crate"}],
        beats_budget=3,
    )
    assert [b.text for b in beats] == ["Wren lifts the crate"]


def test_narrator_hears_what_came_just_before(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You decide" in (request.system or ""):
            return json.dumps({"family": "observe", "focus": "the room"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    first = [r.prompt for r in gateway.sent_requests if "You narrate" in (r.system or "")]
    assert first and not any('key "previously"' in p for p in first)
    before = len(gateway.sent_requests)
    assert _advance(client, ids["world"], 2).status_code == 200
    second = [r.prompt for r in gateway.sent_requests[before:] if "You narrate" in (r.system or "")]
    recaps = [p for p in second if 'key "previously": [recap' in p]
    assert recaps, "the second beat should recall the first"
    assert all("Day 1, sunrise: " in p for p in recaps)  # the first beat, labelled


def test_pronoun_line_states_or_says_how_to_refer() -> None:
    from worldsim.application.orchestration.stage1 import pronoun_line

    world, place = uuid.uuid4(), uuid.uuid4()

    def person(name: str) -> Character:
        return Character(
            id=uuid.uuid4(),
            world_id=world,
            name=name,
            card_version=1,
            location_id=place,
            stamina=80,
            mana=40,
        )

    wren, mira = person("Wren"), person("Mira")
    assert pronoun_line([wren, mira], {mira.id: "she/her"}) == (
        "Pronouns — Mira: she/her; Wren: not stated (use the name or they/them)."
    )


def test_narrator_is_told_how_to_refer_to_everyone_in_the_scene(
    stage1_client: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = stage1_client
    ids = asyncio.run(_seed_two())
    base = _route_for(ids, {})

    def route(request: CompletionRequest) -> str | None:
        if "You decide" in (request.system or ""):
            return json.dumps({"family": "observe", "focus": "the room"})
        return base(request)

    gateway.route = route
    assert _advance(client, ids["world"], 1).status_code == 200
    narrator = [r.prompt for r in gateway.sent_requests if "You narrate" in (r.system or "")]
    assert any('key "pronouns": Pronouns — Wren: not stated' in p for p in narrator)
