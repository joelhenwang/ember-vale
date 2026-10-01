"""Post-commit NarrationGraph checks (owned by S1-NARRATE-001)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from worldsim.application.graphs.narrate import (
    NARRATOR_PROMPT_VERSION,
    NarratorGraphDeps,
    build_narration_graph,
    load_narrator_prompt,
    unfence_json,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.application.ports.model_gateway import ModelUnavailableError
from worldsim.domain.errors import DomainError
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import NARRATOR_FAKE_PROFILE
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

FACTS = [
    {"key": "arrival", "value": "Wren arrives at the market"},
    {"key": "greeting", "value": "Ash waves"},
]


def _deps(gateway: FakeGateway) -> NarratorGraphDeps:
    return NarratorGraphDeps(
        gateway=gateway, profile=NARRATOR_FAKE_PROFILE, system_template=load_narrator_prompt()
    )


def _invocation(event_id: uuid.UUID, **overrides: Any) -> GraphInvocation:
    payload: dict[str, Any] = {
        "event_id": str(event_id),
        "event_committed": True,
        "audience_ids": [],
        "visible_facts": FACTS,
        "beats_budget": 8,
    }
    payload.update(overrides)
    return GraphInvocation(
        graph_name="narrate",
        graph_version="v1",
        task_run_id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        phase_run_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        scene_id=uuid.uuid4(),
        role="narrator",
        profile_version=NARRATOR_FAKE_PROFILE.version,
        prompt_version=NARRATOR_PROMPT_VERSION,
        input=payload,
    )


def _beat(text: str, cited: list[str], speaker: str | None = None) -> dict[str, Any]:
    return {"speaker_id": speaker, "text": text, "cited_fact_keys": cited}


def test_valid_beats_accepted_with_event_linkage() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps([_beat("Wren arrives.", ["arrival"]), _beat("Ash waves.", ["greeting"])])
    )

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["proposal"]["fallback"] is False
    beats = result["proposal"]["beats"]
    assert len(beats) == 2
    assert {b["source_event_id"] for b in beats} == {str(event_id)}
    assert all(b["id"] for b in beats)
    assert beats[0]["cited_fact_keys"] == ["arrival"]


def test_fenced_json_accepted_without_repair() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        "```json\n" + json.dumps([_beat("Wren arrives.", ["arrival"])]) + "\n```"
    )

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["proposal"]["fallback"] is False
    assert result["repair_count"] == 0
    assert result["proposal"]["beats"][0]["cited_fact_keys"] == ["arrival"]


def test_unlabelled_fence_accepted_without_repair() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        "```\n" + json.dumps([_beat("Wren arrives.", ["arrival"])]) + "\n```"
    )

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 0
    assert result["proposal"]["beats"][0]["cited_fact_keys"] == ["arrival"]


def test_incomplete_fence_left_untouched_for_repair() -> None:
    """An unclosed fence is not stripped; the repair path handles it."""
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    unclosed = "```json\n" + json.dumps([_beat("Wren arrives.", ["arrival"])])
    assert unfence_json(unclosed) == unclosed
    gateway.enqueue_text(unclosed)
    gateway.enqueue_text(json.dumps([_beat("Wren arrives.", ["arrival"])]))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1
    assert result["proposal"]["beats"][0]["cited_fact_keys"] == ["arrival"]


def test_commentary_around_fence_left_untouched_for_repair() -> None:
    """Surrounding prose is not stripped; the repair path handles it."""
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    wrapped = (
        "Here is the narration:\n```json\n"
        + json.dumps([_beat("Wren arrives.", ["arrival"])])
        + "\n```"
    )
    assert unfence_json(wrapped) == wrapped
    gateway.enqueue_text(wrapped)
    gateway.enqueue_text(json.dumps([_beat("Wren arrives.", ["arrival"])]))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1
    assert result["proposal"]["beats"][0]["cited_fact_keys"] == ["arrival"]


def test_unrelated_fence_opener_left_untouched() -> None:
    tagged = "```python\n" + json.dumps([_beat("Wren arrives.", ["arrival"])]) + "\n```"
    assert unfence_json(tagged) == tagged


def test_unsupported_fact_repaired_once() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(json.dumps([_beat("Dragons land.", ["dragons"])]))
    gateway.enqueue_text(json.dumps([_beat("Wren arrives.", ["arrival"])]))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1
    assert result["proposal"]["beats"][0]["cited_fact_keys"] == ["arrival"]


def test_repeated_unsupported_falls_back_to_facts() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(json.dumps([_beat("Dragons land.", ["dragons"])]))
    gateway.enqueue_text(json.dumps([_beat("Kings fall.", ["kings"])]))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "fallback"
    assert result["proposal"]["fallback"] is True
    beats = result["proposal"]["beats"]
    assert {tuple(b["cited_fact_keys"]) for b in beats} == {("arrival",), ("greeting",)}
    assert {b["source_event_id"] for b in beats} == {str(event_id)}


def test_outsider_speaker_rejected() -> None:
    event_id = uuid.uuid4()
    outsider = str(uuid.uuid4())
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(json.dumps([_beat("I speak.", ["arrival"], speaker=outsider)]))
    gateway.enqueue_text(json.dumps([_beat("Wren arrives.", ["arrival"])]))
    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1


def test_model_outage_uses_structured_fallback() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_error(ModelUnavailableError("provider down"))

    result = asyncio.run(invoke(build_narration_graph(_deps(gateway)), _invocation(event_id)))

    assert result["status"] == "fallback"
    beats = result["proposal"]["beats"]
    assert len(beats) == 2
    assert "arrival" in beats[0]["text"]


def test_uncommitted_event_refused_without_call() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)

    with pytest.raises(DomainError):
        asyncio.run(
            invoke(
                build_narration_graph(_deps(gateway)), _invocation(event_id, event_committed=False)
            )
        )
    assert gateway.sent_requests == []


def test_beat_budget_enforced() -> None:
    event_id = uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps(
            [
                _beat("One.", ["arrival"]),
                _beat("Two.", ["greeting"]),
                _beat("Three.", ["arrival"]),
            ]
        )
    )
    gateway.enqueue_text(json.dumps([_beat("One.", ["arrival"])]))

    result = asyncio.run(
        invoke(build_narration_graph(_deps(gateway)), _invocation(event_id, beats_budget=1))
    )

    assert result["status"] == "narrated"
    assert len(result["proposal"]["beats"]) == 1


def test_narration_persistence_leaves_projections(migrated_db: None) -> None:
    async def _inner() -> None:
        from worldsim.application.transactions.canonical import (
            CanonicalTransaction,
            CommitRequest,
            canonical_input_hash,
        )
        from worldsim.domain.characters import Character, CharacterCard
        from worldsim.domain.enums import EventType
        from worldsim.domain.ids import (
            new_card_id,
            new_character_id,
            new_command_id,
            new_location_id,
            new_phase_run_id,
            new_world_id,
        )
        from worldsim.domain.narration import NarrationBeat
        from worldsim.domain.phases import PhaseRun
        from worldsim.domain.world import Location, World

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Narr", seed_version="s1-test"))
                home = new_location_id()
                await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
                cid = new_character_id()
                await uow.characters.add_identity(cid, wid, "Wren")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=cid, name="W", version=1)
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=wid,
                        name="Wren",
                        card_version=1,
                        location_id=home,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, wid, "character")
                await uow.versions.ensure(wid, wid, "world")
                run_id = new_phase_run_id()
                await uow.phases.create_run(PhaseRun(id=run_id, world_id=wid, absolute_index=1))
                await uow.commit()
            key = "narrate-probe"
            payload: dict[str, object] = {"note": "probe"}
            tx = CanonicalTransaction(lambda: create_unit_of_work(engine))
            result = await tx.commit(
                CommitRequest(
                    command_id=new_command_id(),
                    world_id=wid,
                    idempotency_key=key,
                    actor_role="system",
                    command_type="advance_phase",
                    expected_versions={str(wid): 0, str(cid): 0},
                    payload=payload,
                    input_hash=canonical_input_hash(
                        {"key": key, "payload": payload, "effects": []}
                    ),
                    absolute_index=1,
                    phase_run_id=run_id,
                    event_type=EventType.WORLD_TICKED,
                    effects=[],
                )
            )
            beat = NarrationBeat(
                id=uuid.uuid4(),
                world_id=wid,
                source_event_id=result.event_id,
                cited_fact_keys=["arrival"],
                text="Wren arrives.",
            )
            async with create_unit_of_work(engine) as uow:
                await uow.scenes.save_narration(beat)
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                stored = await uow.scenes.narrations_for_event(result.event_id)
                assert [b.text for b in stored] == ["Wren arrives."]
                assert stored[0].cited_fact_keys == ["arrival"]
                # Narration changed nothing canonical.
                assert (await uow.characters.get(cid)).version == 0
                assert (await uow.characters.get(cid)).stamina == 80
                assert await uow.events.count_events(wid) == 1
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def _communicate_reaction(
    reactor: uuid.UUID,
    target: uuid.UUID,
    topic: str = "The Market holds stalls, wind, and trade.",
    status: str = "committed",
) -> Any:
    from worldsim.domain.commands import CommunicateAction
    from worldsim.domain.scenes import Reaction

    return Reaction(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        scene_id=uuid.uuid4(),
        reactor_character_id=reactor,
        action=CommunicateAction(
            character_id=reactor,
            snapshot_id=uuid.uuid4(),
            target_character_id=target,
            topic=topic,
        ),
        status=status,  # type: ignore[assignment]
    )


def test_communication_fact_carries_unique_citation_and_speaker() -> None:
    from worldsim.application.graphs.narrate import communication_facts

    ash, wren, outsider = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    spoken = _communicate_reaction(ash, wren, topic='"Market news."')
    facts = communication_facts(
        [spoken],
        {ash: "Ash", wren: "Wren"},
        [str(ash), str(wren)],
    )

    assert len(facts) == 1
    fact = facts[0]
    assert fact["key"] == f"reaction:{spoken.id}"
    assert fact["speaker"] == str(ash)
    assert fact["speaker_name"] == "Ash"
    assert fact["utterance"] == "Market news."
    assert fact["value"] == 'Ash says to Wren: "Market news."'
    # Pending rows, non-speech families, and out-of-audience targets stay out.
    from worldsim.domain.commands import WaitAction
    from worldsim.domain.scenes import Reaction as ReactionRow

    waiting = ReactionRow(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        scene_id=uuid.uuid4(),
        reactor_character_id=ash,
        action=WaitAction(character_id=ash, snapshot_id=uuid.uuid4()),
    )
    assert (
        communication_facts(
            [
                _communicate_reaction(ash, wren, status="pending"),
                _communicate_reaction(ash, outsider),
                waiting,
            ],
            {ash: "Ash", wren: "Wren"},
            [str(ash), str(wren)],
        )
        == []
    )


def test_dialogue_beat_with_wrong_speaker_denied() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    ash, wren = uuid.uuid4(), uuid.uuid4()
    key = "reaction:11111111-2222-4333-8444-555555555555"
    proposal = BeatProposal(
        speaker_id=wren,
        kind="dialogue",  # type: ignore[assignment]
        text="Those are my words.",
        cited_fact_keys=[key],
    )
    denial = beats_valid(
        [proposal],
        visible_keys=frozenset({key}),
        audience_ids=frozenset({str(ash), str(wren)}),
        beats_budget=8,
        fact_speakers={key: str(ash)},
    )
    assert denial is not None
    assert key in denial


def test_fallback_renders_attributed_dialogue() -> None:
    from worldsim.application.graphs.narrate import fallback_beats

    ash = uuid.uuid4()
    event_id, world_id = uuid.uuid4(), uuid.uuid4()
    beats = fallback_beats(
        world_id=world_id,
        scene_id=None,
        event_id=event_id,
        visible_facts=[
            {
                "key": "reaction:abc",
                "value": 'Ash says to Wren: "Market news."',
                "speaker": str(ash),
                "utterance": "Market news.",
            }
        ],
        beats_budget=8,
    )

    assert len(beats) == 1
    assert beats[0].kind == "dialogue"
    assert beats[0].speaker_id == ash
    assert beats[0].cited_fact_keys == ["reaction:abc"]
    assert beats[0].text == "Market news."


def test_instruction_topic_becomes_attributed_summary() -> None:
    from worldsim.application.graphs.narrate import communication_facts

    ash, wren = uuid.uuid4(), uuid.uuid4()
    instructed = _communicate_reaction(ash, wren, topic="Tell Wren about the mill")
    facts = communication_facts(
        [instructed],
        {ash: "Ash", wren: "Wren"},
        [str(ash), str(wren)],
    )

    assert len(facts) == 1
    fact = facts[0]
    assert fact["key"] == f"reaction:{instructed.id}"
    assert fact["speaker"] == str(ash)
    assert "utterance" not in fact
    assert fact["value"] == 'Ash speaks to Wren about "Tell Wren about the mill"'


def test_narrator_prompt_associates_key_name_and_speaker_id() -> None:
    from worldsim.application.graphs.narrate import (
        _fact_view,
        communication_facts,
        render_user_prompt,
    )

    ash, wren = uuid.uuid4(), uuid.uuid4()
    spoken = _communicate_reaction(ash, wren, topic='"Market news."')
    facts = communication_facts(
        [spoken],
        {ash: "Ash", wren: "Wren"},
        [str(ash), str(wren)],
    )
    prompt = render_user_prompt(
        [str(ash), str(wren)],
        [_fact_view(f) for f in facts],
        f"reaction:{spoken.id}",
        None,
        8,
    )

    assert f"reaction:{spoken.id}" in prompt
    assert "Ash" in prompt
    assert str(ash) in prompt


def test_fallback_summarizes_instruction_topic() -> None:
    from worldsim.application.graphs.narrate import fallback_beats

    ash = uuid.uuid4()
    event_id, world_id = uuid.uuid4(), uuid.uuid4()
    beats = fallback_beats(
        world_id=world_id,
        scene_id=None,
        event_id=event_id,
        visible_facts=[
            {
                "key": "reaction:abc",
                "value": 'Ash speaks to Wren about "Tell Wren about the mill"',
                "speaker": str(ash),
            }
        ],
        beats_budget=8,
    )

    assert len(beats) == 1
    assert beats[0].kind == "narration"
    assert beats[0].speaker_id == ash
    assert beats[0].cited_fact_keys == ["reaction:abc"]
    assert "Tell Wren about the mill" in beats[0].text
    assert beats[0].text != "Tell Wren about the mill"

def test_dedupe_narration_facts_collapses_observer_copies() -> None:
    from worldsim.application.graphs.narrate import dedupe_narration_facts

    source = uuid.uuid4()
    assert dedupe_narration_facts(
        [("attempt:wait", "Ash waits", source), ("attempt:wait", "Ash waits", source)]
    ) == [("attempt:wait", "Ash waits")]


def test_dedupe_narration_facts_keeps_distinct_same_family_actions() -> None:
    from worldsim.application.graphs.narrate import dedupe_narration_facts

    first, second = uuid.uuid4(), uuid.uuid4()
    assert dedupe_narration_facts(
        [
            ("attempt:communicate", "Wren asks about the mill", first),
            ("attempt:communicate", "Ash asks about the lamps", second),
        ]
    ) == [
        ("attempt:communicate", "Wren asks about the mill"),
        ("attempt:communicate", "Ash asks about the lamps"),
    ]


def test_dedupe_narration_facts_keeps_identical_text_distinct_actions() -> None:
    from worldsim.application.graphs.narrate import dedupe_narration_facts

    first, second = uuid.uuid4(), uuid.uuid4()
    assert dedupe_narration_facts(
        [("attempt:wait", "Ash waits", first), ("attempt:wait", "Ash waits", second)]
    ) == [("attempt:wait", "Ash waits"), ("attempt:wait", "Ash waits")]


def test_dedupe_narration_facts_passes_through_unprovenanced_facts() -> None:
    from worldsim.application.graphs.narrate import dedupe_narration_facts

    legacy = [("attempt:wait", "Ash waits", None), ("attempt:wait", "Ash waits", None)]
    assert dedupe_narration_facts(legacy) == [
        ("attempt:wait", "Ash waits"),
        ("attempt:wait", "Ash waits"),
    ]


def test_dedupe_narration_facts_is_idempotent() -> None:
    from worldsim.application.graphs.narrate import dedupe_narration_facts

    source = uuid.uuid4()
    facts = [
        ("attempt:wait", "Ash waits", source),
        ("attempt:wait", "Ash waits", source),
        ("attempt:communicate", "Wren asks", uuid.uuid4()),
        ("dnd-sheet:ash", "level 1", None),
    ]
    once = dedupe_narration_facts(facts)
    assert dedupe_narration_facts([(k, v, None) for k, v in once]) == once


def test_committed_dialogue_pair_retains_speakers_and_citations() -> None:
    from worldsim.application.graphs.narrate import communication_facts, fallback_beats

    ash, wren = uuid.uuid4(), uuid.uuid4()
    spoken = _communicate_reaction(ash, wren, topic='"Market news."')
    instructed = _communicate_reaction(wren, ash, topic="Tell Ash about the mill")
    facts = communication_facts(
        [spoken, instructed],
        {ash: "Ash", wren: "Wren"},
        [str(ash), str(wren)],
    )
    assert [f['key'] for f in facts] == [f"reaction:{spoken.id}", f"reaction:{instructed.id}"]
    beats = fallback_beats(
        world_id=uuid.uuid4(),
        scene_id=None,
        event_id=uuid.uuid4(),
        visible_facts=facts,
        beats_budget=8,
    )
    assert len(beats) == 2
    assert beats[0].kind == "dialogue"
    assert beats[0].speaker_id == ash
    assert beats[0].text == "Market news."
    assert beats[0].cited_fact_keys == [f"reaction:{spoken.id}"]
    assert beats[1].kind == "narration"
    assert beats[1].speaker_id == wren
    assert beats[1].cited_fact_keys == [f"reaction:{instructed.id}"]




AUDIENCE_1D6C = (
"Audience: 17f19638-b398-45e1-8074-17befed1f719,"
" a19a3069-496e-4751-993b-c9ae9566000a."
)


def test_parse_audience_strips_sentence_period() -> None:
    from worldsim.application.graphs.narrate import parse_narration_context

    audience, _keys, _budget = parse_narration_context(AUDIENCE_1D6C + chr(10))
    assert audience == frozenset({
"17f19638-b398-45e1-8074-17befed1f719",
"a19a3069-496e-4751-993b-c9ae9566000a",
    })


def test_parse_keys_supports_legacy_unquoted_format() -> None:
    from worldsim.application.graphs.narrate import parse_narration_context

    prompt = chr(10).join([
"Audience: 61777125-77b7-4233-aa68-5827554491ee, fbb1c051-8fb9-4dae-b800-b198c7249f3e.",
"Visible facts:",
"- attempt:communicate: Wren says to Ash: Ask Ash whether the stalls are open yet.",
"- attempt:wait: Ash waits",
    ])
    _audience, keys, _budget = parse_narration_context(prompt)
    assert keys == frozenset({"attempt:communicate", "attempt:wait"})


def test_parse_keys_supports_quoted_format_and_ignores_roster() -> None:
    from worldsim.application.graphs.narrate import parse_narration_context

    prompt = chr(10).join([
"Audience: 17f19638-b398-45e1-8074-17befed1f719, a19a3069-496e-4751-993b-c9ae9566000a.",
"Visible facts:",
'- key "attempt:communicate": Wren says to Ash: Ash, one last probe question for the road?',
'- key "reaction:b0130c69-76d5-5852-aac8-e3bac5f5e863": Ash says to Wren: "One more? Go on then."',
"- Ash (id: 17f19638-b398-45e1-8074-17befed1f719)",
    ])
    _audience, keys, _budget = parse_narration_context(prompt)
    assert keys == frozenset({
"attempt:communicate",
"reaction:b0130c69-76d5-5852-aac8-e3bac5f5e863",
    })


def test_parsed_context_accepts_exact_ids_and_rejects_foreign() -> None:
    from worldsim.application.graphs.narrate import beats_valid, parse_narration_context
    from worldsim.domain.narration import BeatProposal

    prompt = AUDIENCE_1D6C + chr(10) + '- key "attempt:wait": Ash waits'
    audience, keys, budget = parse_narration_context(prompt)
    good = BeatProposal(text="Ash waits.", cited_fact_keys=["attempt:wait"], kind="narration")
    assert beats_valid(
        [good], visible_keys=keys, audience_ids=audience, beats_budget=budget
    ) is None
    foreign_speaker = BeatProposal(
        text="Ash waits.", cited_fact_keys=["attempt:wait"], kind="narration",
        speaker_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
    )
    assert beats_valid(
        [foreign_speaker], visible_keys=keys, audience_ids=audience, beats_budget=budget
    ) is not None
    invented_key = BeatProposal(
        text="Ash waits.", cited_fact_keys=["attempt:wait: Ash waits"], kind="narration"
    )
    assert beats_valid(
        [invented_key], visible_keys=keys, audience_ids=audience, beats_budget=budget
    ) is not None




def test_dedupe_prompt_lines_keeps_first_fact_copies() -> None:
    from worldsim.application.graphs.narrate import dedupe_prompt_lines

    prompt = chr(10).join([
"Event e in scene s.",
"Audience: a, b.",
"Visible facts:",
'- key "attempt:wait": Ash waits',
'- key "attempt:communicate": Wren asks',
'- key "attempt:wait": Ash waits',
"- Ash (id: a)",
    ])
    out = dedupe_prompt_lines(prompt).splitlines()
    assert out.count('- key "attempt:wait": Ash waits') == 1
    assert out.index('- key "attempt:communicate": Wren asks') == 4
    assert "- Ash (id: a)" in out
    assert "Audience: a, b." in out


def test_beats_valid_enforces_mapped_speakers() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    wren, ash = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"attempt:communicate"})
    audience = frozenset({str(wren), str(ash)})
    matched = BeatProposal(
        text="Wren asks.", cited_fact_keys=["attempt:communicate"], kind="narration",
        speaker_id=wren,
    )
    assert beats_valid(
        [matched], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"attempt:communicate": str(wren)},
    ) is None
    # The wrong speaker is the OTHER in-audience character: audience
    # validation alone accepts it, so only source attribution rejects it.
    mismatched = BeatProposal(
        text="Wren asks.", cited_fact_keys=["attempt:communicate"], kind="narration",
        speaker_id=ash,
    )
    assert beats_valid(
        [mismatched], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"attempt:communicate": str(wren)},
    ) == "speaker does not match cited source: attempt:communicate"




def test_speech_eligible_keys_only_quoted_speech() -> None:
    from worldsim.application.graphs.narrate import speech_eligible_keys

    facts = [
        {"key": "attempt:communicate", "value": "Wren asks"},
        {"key": "reaction:s1", "value": 'Wren speaks to Ash about "stalls"', "speaker": "w"},
        {
            "key": "reaction:s2",
            "value": 'Ash says to Wren: "One more?"',
            "speaker": "a",
            "utterance": "One more?",
        },
    ]
    assert speech_eligible_keys(facts) == frozenset({"reaction:s2"})


def test_dialogue_from_attempt_is_rejected_even_with_right_speaker() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    wren, ash = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"attempt:communicate"})
    audience = frozenset({str(wren), str(ash)})
    voiced_attempt = BeatProposal(
        text="Wren says to Ash: 'Ask Ash what the Market holds today.'",
        cited_fact_keys=["attempt:communicate"], kind="dialogue",
        speaker_id=wren,
    )
    assert beats_valid(
        [voiced_attempt], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"attempt:communicate": str(wren)},
        speech_keys=frozenset(),
    ) == "dialogue cites non-speech evidence: ['attempt:communicate']"


def test_dialogue_from_attempt_reports_speech_before_speaker() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    wren, ash = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"attempt:communicate"})
    audience = frozenset({str(wren), str(ash)})
    others_words = BeatProposal(
        text="Wren turns to Ash, asking.",
        cited_fact_keys=["attempt:communicate"], kind="dialogue",
        speaker_id=ash,
    )
    assert beats_valid(
        [others_words], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"attempt:communicate": str(wren)},
        speech_keys=frozenset(),
    ) == "dialogue cites non-speech evidence: ['attempt:communicate']"


def test_dialogue_from_unquoted_topic_is_rejected() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    wren, ash = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"reaction:s1"})
    audience = frozenset({str(wren), str(ash)})
    quoted_topic = BeatProposal(
        text="Tell Ash about the mill.", cited_fact_keys=["reaction:s1"], kind="dialogue",
        speaker_id=wren,
    )
    assert beats_valid(
        [quoted_topic], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"reaction:s1": str(wren)},
        speech_keys=frozenset(),
    ) == "dialogue cites non-speech evidence: ['reaction:s1']"


def test_dialogue_from_quoted_speech_is_accepted() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    ash, wren = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"reaction:s2", "attempt:wait"})
    audience = frozenset({str(wren), str(ash)})
    spoken = BeatProposal(
        text="One more?", cited_fact_keys=["reaction:s2"], kind="dialogue",
        speaker_id=ash,
    )
    assert beats_valid(
        [spoken], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"reaction:s2": str(ash)},
        speech_keys=frozenset({"reaction:s2"}),
    ) is None




def test_dialogue_without_speaker_is_rejected() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    ash, wren = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"reaction:s2"})
    audience = frozenset({str(wren), str(ash)})
    speakers = {"reaction:s2": str(ash)}
    speech = frozenset({"reaction:s2"})
    omitted = BeatProposal(text="One more?", cited_fact_keys=["reaction:s2"], kind="dialogue")
    assert beats_valid(
        [omitted], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers=speakers, speech_keys=speech,
    ) == "dialogue requires a speaker matching cited speech"
    null = BeatProposal(
        text="One more?", cited_fact_keys=["reaction:s2"], kind="dialogue", speaker_id=None,
    )
    assert beats_valid(
        [null], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers=speakers, speech_keys=speech,
    ) == "dialogue requires a speaker matching cited speech"


def test_dialogue_with_wrong_in_audience_speaker_is_rejected() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    ash, wren = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"reaction:s2"})
    audience = frozenset({str(wren), str(ash)})
    borrowed = BeatProposal(
        text="One more?", cited_fact_keys=["reaction:s2"], kind="dialogue",
        speaker_id=wren,
    )
    assert beats_valid(
        [borrowed], visible_keys=keys, audience_ids=audience, beats_budget=8,
        fact_speakers={"reaction:s2": str(ash)},
        speech_keys=frozenset({"reaction:s2"}),
    ) == "speaker does not match cited source: reaction:s2"


def test_narration_summary_keeps_null_speaker() -> None:
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    ash, wren = uuid.uuid4(), uuid.uuid4()
    keys = frozenset({"attempt:wait"})
    audience = frozenset({str(wren), str(ash)})
    summary = BeatProposal(text="Ash waits.", cited_fact_keys=["attempt:wait"], kind="narration")
    assert beats_valid(
        [summary], visible_keys=keys, audience_ids=audience, beats_budget=8,
    ) is None

def test_render_marks_communicate_attempt_as_topic() -> None:
    from worldsim.application.graphs.narrate import _render_fact_line

    line = _render_fact_line(
        {"key": "attempt:communicate", "value": "Wren says to Ash: dawn patrol"}
    )
    assert line == (
        '- key "attempt:communicate": [attempt \u2014 narration-only] '
        "Wren attempts to communicate with Ash; topic: dawn patrol"
    )


def test_render_marks_wait_attempt_narration_only() -> None:
    from worldsim.application.graphs.narrate import _render_fact_line

    line = _render_fact_line({"key": "attempt:wait", "value": "Ash waits"})
    assert "[attempt \u2014 narration-only]" in line
    assert line.endswith("Ash waits")


def test_render_marks_speech_eligible_with_speaker() -> None:
    from worldsim.application.graphs.narrate import _render_fact_line

    line = _render_fact_line(
        {
            "key": "reaction:s2",
            "value": 'Ash says to Wren: "One more?"',
            "speaker": "a",
            "speaker_name": "Ash",
            "utterance": "One more?",
        }
    )
    assert "[quoted speech \u2014 dialogue-eligible]" in line
    assert '"One more?"' in line
    assert "(speaker Ash, id: a)" in line


def test_render_marks_summary_narration_only() -> None:
    from worldsim.application.graphs.narrate import _render_fact_line

    line = _render_fact_line(
        {
            "key": "reaction:s1",
            "value": 'Wren speaks to Ash about "stalls"',
            "speaker": "w",
            "speaker_name": "Wren",
        }
    )
    assert "[attributed summary \u2014 narration-only]" in line
    assert "dialogue-eligible" not in line


def test_rendered_categorized_prompt_parses() -> None:
    from worldsim.application.graphs.narrate import (
        parse_narration_context,
        render_user_prompt,
    )

    prompt = render_user_prompt(
        ["a", "w"],
        [
            {"key": "attempt:communicate", "value": "Wren says to Ash: dawn patrol"},
            {
                "key": "reaction:s2",
                "value": 'Ash says to Wren: "One more?"',
                "speaker": "a",
                "speaker_name": "Ash",
                "utterance": "One more?",
            },
        ],
        "e1",
        "s1",
        8,
    )
    audience, keys, budget = parse_narration_context(prompt)
    assert audience == frozenset({"a", "w"})
    assert keys == frozenset({"attempt:communicate", "reaction:s2"})
    assert budget == 8


def test_repair_instruction_names_fix_and_bars_substitution() -> None:
    from worldsim.application.graphs.narrate import repair_instruction

    text = repair_instruction(
        "dialogue cites non-speech evidence: ['attempt:communicate']"
    )
    assert "narrator prose" in text
    assert "same key" in text
    assert "different speech key" in text
    assert "matching the response schema" in text


def test_graph_repair_sends_actionable_instruction() -> None:
    wren, ash = uuid.uuid4(), uuid.uuid4()
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(
        json.dumps(
            [
                {
                    "text": "Wren asks.",
                    "cited_fact_keys": ["attempt:communicate"],
                    "kind": "dialogue",
                    "speaker_id": str(wren),
                }
            ]
        )
    )
    gateway.enqueue_text(json.dumps([_beat("Wren asks.", ["attempt:communicate"])]))

    result = asyncio.run(
        invoke(
            build_narration_graph(_deps(gateway)),
            _invocation(
                uuid.uuid4(),
                audience_ids=[str(wren), str(ash)],
                visible_facts=[
                    {"key": "attempt:communicate", "value": "Wren asks"},
                    {"key": "attempt:wait", "value": "Ash waits"},
                ],
            ),
        )
    )

    assert result["status"] == "narrated"
    assert result["repair_count"] == 1
    repair_prompt = gateway.sent_requests[1].prompt
    assert "narrator prose" in repair_prompt
    assert "different speech key" in repair_prompt


def test_structural_acceptance_does_not_imply_fidelity() -> None:
    """Retained semantic-failure example (paid Nemo eval, quoted-question).

    This accepted repair output passes structural validation while putting
    Wren's question ("Where is the mill?", from the attempt fact) into
    Ash's mouth under Ash's valid reaction citation. beats_valid scope
    ends at structure; wording fidelity needs separate review. Never
    loosen validation to "fix" this case — it is correctly accepted.
    """
    from worldsim.application.graphs.narrate import beats_valid
    from worldsim.domain.narration import BeatProposal

    ash = uuid.UUID("2319cc72-5188-4f37-a0ae-e6698d660ccd")
    wren = uuid.UUID("5e00990a-fb08-4505-84d2-6397b4a6dd3e")
    key = "reaction:893a99c0-3096-5d23-a287-acc61c39202e"
    misvoiced = BeatProposal(
        text="Where is the mill?",
        cited_fact_keys=[key],
        kind="dialogue",  # type: ignore[assignment]
        speaker_id=ash,
    )
    assert (
        beats_valid(
            [misvoiced],
            visible_keys=frozenset({"attempt:communicate", "attempt:wait", key}),
            audience_ids=frozenset({str(ash), str(wren)}),
            beats_budget=8,
            fact_speakers={key: str(ash)},
            speech_keys=frozenset({key}),
        )
        is None
    )
    assert misvoiced.text != "Past the bridge, second left."

def test_repair_for_missing_speaker_keeps_dialogue() -> None:
    from worldsim.application.graphs.narrate import repair_instruction

    text = repair_instruction("dialogue requires a speaker matching cited speech")
    assert "exact speaker" in text
    assert "supported utterance" in text
    assert "invalid as dialogue" not in text


def test_repair_for_wrong_speaker_keeps_dialogue() -> None:
    from worldsim.application.graphs.narrate import repair_instruction

    text = repair_instruction("speaker does not match cited source: reaction:s")
    assert "exact speaker" in text
    assert "borrow another voice" in text
    assert "invalid as dialogue" not in text


def test_repair_for_invented_key_drops_it() -> None:
    from worldsim.application.graphs.narrate import repair_instruction

    text = repair_instruction("unsupported facts cited: ['dragons']")
    assert "drop" in text
    assert "invalid as dialogue" not in text
    assert "same key" not in text


def test_repair_for_schema_error_names_format() -> None:
    from worldsim.application.graphs.narrate import repair_instruction

    text = repair_instruction("attempt 0: 2 schema errors")
    assert "exactly matching the response schema" in text
    assert "invalid as dialogue" not in text


def _repair_prompt_for(
    first: str, visible_facts: list, audience_ids: list | None = None
) -> str:
    if audience_ids is None:
        audience_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    gateway = FakeGateway(profile=NARRATOR_FAKE_PROFILE)
    gateway.enqueue_text(first)
    gateway.enqueue_text(json.dumps([_beat("Ash waits.", ["attempt:wait"])]))
    result = asyncio.run(
        invoke(
            build_narration_graph(_deps(gateway)),
            _invocation(
                uuid.uuid4(),
                audience_ids=audience_ids,
                visible_facts=visible_facts,
            ),
        )
    )
    assert result["status"] == "narrated"
    assert result["repair_count"] == 1
    return gateway.sent_requests[1].prompt


def _speech_facts(ash: str) -> list:
    return [
        {"key": "attempt:wait", "value": "Ash waits"},
        {
            "key": "reaction:s",
            "value": 'Ash says to Wren: "One more?"',
            "speaker": ash,
            "speaker_name": "Ash",
            "utterance": "One more?",
        },
    ]


def test_graph_repair_for_missing_speaker_preserves_dialogue() -> None:
    ash = str(uuid.uuid4())
    prompt = _repair_prompt_for(
        json.dumps(
            [
                {
                    "text": "One more?",
                    "cited_fact_keys": ["reaction:s"],
                    "kind": "dialogue",
                    "speaker_id": None,
                }
            ]
        ),
        _speech_facts(ash),
    )
    assert "dialogue requires a speaker matching cited speech" in prompt
    assert "exact speaker" in prompt
    assert "invalid as dialogue" not in prompt


def test_graph_repair_for_wrong_speaker_preserves_dialogue() -> None:
    ash = str(uuid.uuid4())
    wren = str(uuid.uuid4())
    prompt = _repair_prompt_for(
        json.dumps(
            [
                {
                    "text": "One more?",
                    "cited_fact_keys": ["reaction:s"],
                    "kind": "dialogue",
                    "speaker_id": wren,
                }
            ]
        ),
        _speech_facts(ash),
        audience_ids=[ash, wren],
    )
    assert "speaker does not match cited source" in prompt
    assert "exact speaker" in prompt
    assert "invalid as dialogue" not in prompt


def test_graph_repair_for_invented_key_drops_it() -> None:
    prompt = _repair_prompt_for(
        json.dumps([_beat("Dragons land.", ["dragons"])]),
        [{"key": "attempt:wait", "value": "Ash waits"}],
    )
    assert "drop" in prompt
    assert "invalid as dialogue" not in prompt


def test_graph_repair_for_malformed_json_names_format() -> None:
    prompt = _repair_prompt_for(
        "not json at all",
        [{"key": "attempt:wait", "value": "Ash waits"}],
    )
    assert "exactly matching the response schema" in prompt
    assert "invalid as dialogue" not in prompt
