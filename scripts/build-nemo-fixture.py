"""Build the bounded Nemo narrator fixture (zero model spend).

Runs the real Stage1Orchestrator with scripted gateways over a 16-scenario
matrix (quoted speech, topic-only communication, attempts without speech,
both speakers, plus outsider-target reaction, multiple reactions, observe
alongside speech, long/one-word/apostrophe utterances); the narrator
gateway returns a canned VALID beat so each phase completes narrated.
Captures each initial narrator CompletionRequest and rebuilds authoritative
metadata from committed rows with production functions (prompt rebuild
equality is asserted per scenario).

Writes docs/evidence/latency-eval-001/fixture-narrator-nemo-007.json
(or the name in argv[1]).
Requires a reachable PostgreSQL (WORLDSIM_DATABASE__URL); builds a
migration-head template and per-scenario scratch clones, dropped after.
"""
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))
sys.path.insert(0, str(REPO / "backend" / "tests"))

from fixtures.postgres import (
    clone_database,
    create_scratch_database,
    drop_scratch_database,
    replace_database,
    scratch_name,
    upgrade_head,
)
from test_stage1_orchestration import (
    _orchestrator,
    _role_gateways,
    _seed,
    _set_grant,
)
from worldsim.application.graphs.narrate import (
    NARRATOR_PROMPT_VERSION,
    _fact_view,
    communication_facts,
    dedupe_narration_facts,
    load_narrator_prompt,
    attempt_speech_facts,
    citation_aliases,
    parse_narration_context,
    render_system_prompt,
    render_user_prompt,
    speech_eligible_keys,
)
from worldsim.application.orchestration.service import (
    derive_run_id,
    derive_snapshot_id,
)
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
)
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.commands import CommunicateAction
from worldsim.domain.enums import LifeStatus
from worldsim.domain.ids import new_card_id, new_character_id
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import (
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings


def _make_template() -> tuple[str, str]:
    settings = Settings()
    name = scratch_name("nemo_fixture_template")
    create_scratch_database(settings, name)
    previous = os.environ.get("WORLDSIM_DATABASE__URL")
    os.environ["WORLDSIM_DATABASE__URL"] = replace_database(settings.database.url, name)
    try:
        upgrade_head()
    finally:
        if previous is None:
            os.environ.pop("WORLDSIM_DATABASE__URL", None)
        else:
            os.environ["WORLDSIM_DATABASE__URL"] = previous
    return settings.database.url, name

ZERO_SNAP = "00000000-0000-0000-0000-000000000000"


async def _seed_marlow(ids: dict, *, dead: bool) -> UUID:
    """Third world character for outsider/multi-reaction scenes (mirrors _seed)."""
    engine = create_engine(Settings())
    try:
        async with create_unit_of_work(engine) as uow:
            marlow = new_character_id()
            await uow.characters.add_identity(marlow, ids["world"], "Marlow")
            await uow.characters.add_card(
                CharacterCard(id=new_card_id(), character_id=marlow, name="Marlow", version=1)
            )
            await uow.characters.add_state(
                Character(
                    id=marlow,
                    world_id=ids["world"],
                    name="Marlow",
                    card_version=1,
                    location_id=ids["hearth"],
                    stamina=80,
                    mana=40,
                    **({"life_status": LifeStatus.DEAD} if dead else {}),
                )
            )
            await uow.versions.ensure(marlow, ids["world"], "character")
            await uow.commit()
            return marlow
    finally:
        await engine.dispose()

SCENARIOS = [
    {"name": "quoted-speech-ash", "controller": "wren", "ask": "dawn patrol",
     "answer": ("communicate", '"Dawn patrol passed at first light."')},
    {"name": "topic-only-ash", "controller": "wren", "ask": "dawn patrol",
     "answer": ("communicate", "Tell Wren about the mill")},
    {"name": "attempts-ash-waits", "controller": "wren", "ask": "dawn patrol",
     "answer": ("wait", None)},
    {"name": "attempts-wren-waits", "controller": "ash", "ask": "dawn patrol",
     "answer": ("wait", None)},
    {"name": "quoted-speech-wren", "controller": "ash", "ask": "dawn patrol",
     "answer": ("communicate", '"The mill road is clear."')},
    {"name": "topic-only-wren", "controller": "ash", "ask": "dawn patrol",
     "answer": ("communicate", "Tell Ash about the lamps")},
    {"name": "quoted-question", "controller": "wren", "ask": '"Where is the mill?"',
     "answer": ("communicate", '"Past the bridge, second left."')},
    {"name": "mill-brief", "controller": "wren", "ask": "mill stores",
     "answer": ("communicate", '"Grain and oilskins."')},
    {"name": "lighthouse", "controller": "wren", "ask": "Who keeps the lighthouse at night?",
     "answer": ("communicate", '"Old Marlow, if the lamp is still lit."')},
    {"name": "stalls", "controller": "wren", "ask": "Ask Ash whether the stalls are open yet.",
     "answer": ("communicate", '"Stalls open at second bell."')},
    {"name": "outsider-reaction", "controller": "wren", "ask": "dawn patrol",
     "answer": ("communicate", '"Rest easy, Marlow. The north road is open again."'),
     "third": "dead", "answer_target": "third"},
    {"name": "two-reactions", "controller": "wren", "ask": "dawn patrol",
     "answer": ("communicate", '"Dawn bell means the first stalls are opening."'),
     "third": "alive",
     "third_intent": ("communicate", '"Road is clear past the hearth."', "ash"),
     "third_answer": ("communicate", '"Aye, and mind the loose stones past the bridge."')},
    {"name": "observe-alongside-speech", "controller": "wren", "ask": "dawn patrol",
     "answer": ("communicate", '"Dawn bell means the market\'s waking."'),
     "third": "alive", "third_intent": ("observe", "Ash")},
    {"name": "long-utterance", "controller": "wren",
     "ask": "What should we watch for on the road ahead?",
     "answer": ("communicate", ('"Dawn bell means the market is waking early today, so hurry down '
                'with coin and basket before the best bread and freshest fish are gone '
                'from the stalls."'))},
    {"name": "one-word-reply", "controller": "wren",
     "ask": "Is the old bridge safe to cross?",
     "answer": ("communicate", '"No."')},
    {"name": "apostrophe-quote", "controller": "wren",
     "ask": "What news from the mill, Ash?",
     "answer": ("communicate", '"It\'s still standing, unless someone\'s moved it."')},
]


def _wait_json(actor: UUID, snapshot: UUID) -> str:
    return json.dumps(
        {"family": "wait", "character_id": str(actor), "snapshot_id": str(snapshot)}
    )


def run_one(spec: dict) -> dict:
    async def _inner() -> dict:
        ids = await _seed()
        controller = ids[spec["controller"]]
        other = ids["ash"] if spec["controller"] == "wren" else ids["wren"]
        third_mode = spec.get("third")
        marlow: UUID | None = None
        if third_mode is not None:
            marlow = await _seed_marlow(ids, dead=third_mode == "dead")
            ids["marlow"] = marlow
        await _set_grant(ids, "player", controller)
        gateways = _role_gateways(ids)
        base_character = gateways["character"].route
        base_reaction = gateways["reaction"].route
        c_name = "Wren" if spec["controller"] == "wren" else "Ash"
        snap = derive_snapshot_id(derive_run_id(ids["world"], 1))

        def character_route(request: CompletionRequest) -> str | None:
            if f"identity>>{c_name}" in request.prompt:
                raise AssertionError(f"controlled {c_name} must not reach model decision")
            if third_mode == "alive" and "identity>>Marlow" in request.prompt:
                tintent = spec.get("third_intent")
                assert tintent is not None, "living third character needs a scripted intent"
                if tintent[0] == "communicate":
                    ttarget = {"ash": ids["ash"], "wren": ids["wren"]}.get(
                        tintent[2] if len(tintent) > 2 else "", controller)
                    return json.dumps(
                        {
                            "family": "communicate",
                            "character_id": str(marlow),
                            "snapshot_id": str(snap),
                            "target_character_id": str(ttarget),
                            "topic": tintent[1],
                        }
                    )
                if tintent[0] == "observe":
                    return json.dumps(
                        {
                            "family": "observe",
                            "character_id": str(marlow),
                            "snapshot_id": str(snap),
                            "focus": tintent[1],
                        }
                    )
                raise AssertionError(f"unknown third intent kind: {tintent[0]}")
            assert base_character is not None
            return base_character(request)

        kind, topic = spec["answer"]
        # Production asks every other participant to react once per attempt,
        # so a three-person scene issues several reaction calls per reactor.
        # Each scripted reactor speaks on its first call and waits afterwards;
        # answering every call with the same line duplicated the speech facts.
        spoken: set[str] = set()

        def reaction_route(request: CompletionRequest) -> str | None:
            if f"identity>>{c_name}" in request.prompt:
                raise AssertionError(f"controlled {c_name} must not reach model reaction")
            if third_mode == "alive" and "identity>>Marlow" in request.prompt:
                tanswer = spec.get("third_answer", ("wait", None))
                if tanswer[0] == "communicate" and "marlow" not in spoken:
                    spoken.add("marlow")
                    return json.dumps(
                        {
                            "family": "communicate",
                            "character_id": str(marlow),
                            "snapshot_id": ZERO_SNAP,
                            "target_character_id": str(controller),
                            "topic": tanswer[1],
                        }
                    )
                return _wait_json(marlow, UUID(ZERO_SNAP))
            # Uncontrolled side answers per scenario (or falls back to base).
            me = other
            target = marlow if spec.get("answer_target") == "third" else controller
            if kind == "communicate" and "other" in spoken:
                return _wait_json(me, UUID(ZERO_SNAP))
            if kind == "communicate":
                spoken.add("other")
                return json.dumps(
                    {
                        "family": "communicate",
                        "character_id": str(me),
                        "snapshot_id": ZERO_SNAP,
                        "target_character_id": str(target),
                        "topic": topic,
                    }
                )
            assert base_reaction is not None
            return base_reaction(request)

        def narrator_route(request: CompletionRequest) -> str | None:
            _aud, keys, _b = parse_narration_context(request.prompt)
            attempts = sorted(k for k in keys if k.startswith("attempt:"))
            cited = attempts[0] if attempts else min(keys)
            return json.dumps(
                [{"text": "The watch turns over.", "cited_fact_keys": [cited],
                  "kind": "narration", "speaker_id": None}]
            )

        gateways["character"].route = character_route
        gateways["reaction"].route = reaction_route
        gateways["narrator"].route = narrator_route

        if spec["controller"] == "wren":
            player = {controller: CommunicateAction(
                character_id=controller, snapshot_id=snap,
                target_character_id=other, topic=spec["ask"])}
        else:
            player = {controller: CommunicateAction(
                character_id=controller, snapshot_id=snap,
                target_character_id=other, topic=spec["ask"])}
        report = await _orchestrator(gateways).advance_phase(ids["world"], 1, player)
        assert not report.duplicate
        reqs = gateways["narrator"].sent_requests
        assert reqs, f"{spec['name']}: no narrator call captured"
        initial = reqs[0]
        scene = report.scenes[0]

        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                row = await uow.scenes.get_scene(scene.scene_id)
                observations = await uow.perception.observations_for_event(scene.event_id)
                reactions = await uow.scenes.reactions_for_scene(scene.scene_id)
                intents = [await uow.scenes.get_intent(i) for i in row.intent_ids]
                characters = await uow.characters.list_for_world(ids["world"])
        finally:
            await engine.dispose()

        participants = [str(p.character_id) for p in row.participants]
        names = {c.id: c.name for c in characters}
        sourced = [(f.key, f.value, obs.source_id) for obs in observations for f in obs.facts]
        facts = [{"key": k, "value": v} for k, v in dedupe_narration_facts(sourced)]
        facts.extend(attempt_speech_facts(intents, names, participants))
        facts.extend(communication_facts(reactions, names, participants))
        views = [_fact_view(f) for f in facts]
        rebuilt = render_user_prompt(
            participants, views, str(scene.event_id),
            str(scene.scene_id), row.beat_budget, None)
        assert rebuilt == initial.prompt, f"{spec['name']}: rebuilt prompt differs"
        assert initial.system == render_system_prompt(load_narrator_prompt())
        audience, keys, budget = parse_narration_context(initial.prompt)
        return {
            "scenario": spec["name"],
            "role": "narrator",
            "prompt_hash": hashlib.sha256(initial.prompt.encode("utf-8")).hexdigest(),
            "prompt": initial.prompt,
            "system": initial.system,
            "max_tokens": initial.max_tokens,
            "captured_temperature": initial.temperature,
            "captured_top_p": initial.top_p,
            "captured_top_k": initial.top_k,
            "json_mode": initial.json_mode,
            "audience": sorted(audience),
            # Real keys; the prompt shows reaction keys by alias.
            "visible_keys": sorted({str(f["key"]) for f in views}),
            "aliases": citation_aliases(views),
            "speech_keys": sorted(speech_eligible_keys(facts)),
            "speakers": {f["key"]: f["speaker"] for f in facts if "speaker" in f},
            "utterances": {f["key"]: f["utterance"] for f in facts if "utterance" in f},
            "speaker_names": {str(cid): n for cid, n in names.items()
                              if str(cid) in set(participants)},
            "beat_budget": budget,
            "sources": {
                key: sorted({str(obs.source_id) for obs in observations
                             for f in obs.facts if f.key == key})
                for key in sorted({f.key for obs in observations for f in obs.facts})
            } | {
                f"reaction:{r.id}": {
                    "reaction_id": str(r.id),
                    "reactor": str(r.reactor_character_id),
                    "kind": type(r.action).__name__,
                    "target": str(getattr(r.action, "target_character_id", "")),
                    "topic": str(getattr(r.action, "topic", "")),
                    "status": str(r.status),
                }
                for r in reactions
            },
            "event_id": str(scene.event_id),
            "scene_id": str(scene.scene_id),
            "narrator_calls": len(reqs),
            "phase_status": [s.narration for s in report.scenes],
        }

    return asyncio.run(_inner())


if __name__ == "__main__":
    base_url, template = _make_template()
    out = []
    try:
        for spec in SCENARIOS:
            name = scratch_name("nemo_fixture_run")
            clone_database(Settings(), template, name)
            os.environ["WORLDSIM_DATABASE__URL"] = replace_database(base_url, name)
            try:
                out.append(run_one(spec))
            finally:
                drop_scratch_database(Settings(), name)
    finally:
        drop_scratch_database(Settings(), template)
    prompts = [o["prompt"] for o in out]
    assert len(set(prompts)) == len(out), "scenarios must be distinct"
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO, check=True
    ).stdout.strip()
    doc = {
        "source": "production assembly (build-nemo-fixture.py, zero model spend)",
        "code_revision": revision,
        "prompt_version": NARRATOR_PROMPT_VERSION,
        "sampling_captured": {
            "temperature": out[0]["captured_temperature"],
            "top_p": out[0]["captured_top_p"],
            "top_k": out[0]["captured_top_k"],
            "json_mode": out[0]["json_mode"],
            "max_tokens": out[0]["max_tokens"],
        },
        "items": out,
    }
    name = sys.argv[1] if len(sys.argv) > 1 else "fixture-narrator-nemo-007.json"
    dest = REPO / "docs" / "evidence" / "latency-eval-001" / name
    dest.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for o in out:
        print(f"{o['scenario']}: keys={o['visible_keys']} speech={o['speech_keys']} "
              f"calls={o['narrator_calls']} status={o['phase_status']}")
    print(f"wrote {dest} n={len(out)}")
