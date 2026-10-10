"""Watched adventures: a story nobody plays can have fights too (watchparty).

The first four cast members form the party, each linked to their own
character with a calling read from their card; nobody waits on level-up
choices, and every member in a scene fights beside the others.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from test_combat_depth_2 import _families
from test_companions import _ash, _heal_all
from test_party_combat import _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.application.ports.writer import Written
from worldsim.application.stories.create import suggest_party_callings
from worldsim.application.stories.validation import validate_draft
from worldsim.domain.party import Monster, PartyMember, chooser_keys, party_note, present_keys
from worldsim.domain.stories import DraftPayload
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

WATCHED = {"role": "watcher", "adventure": {}}
WATCHER = {"X-Worldsim-Role": "watcher"}


def _payload(mode: dict[str, Any]) -> DraftPayload:
    return DraftPayload.model_validate(
        {
            "world": {"preset_id": "20000000-0000-4000-8000-000000000001"},
            "cast": [{"instance_key": "a", "name": "Wren"}, {"instance_key": "b", "name": "Ash"}],
            "mode": mode,
        }
    )


def test_a_watched_party_needs_no_hero_calling() -> None:
    assert validate_draft(_payload(WATCHED)) == []
    # Director and God seats may watch an adventure too.
    assert validate_draft(_payload({"role": "director", "adventure": {}})) == []
    told = validate_draft(
        _payload({"role": "watcher", "adventure": {"race": "elf", "character_class": "wizard"}})
    )
    assert told == ["a watched party's callings come from the cast, not the draft"]
    # A played hero still names both.
    played = validate_draft(
        _payload({"role": "player", "controlled_cast_key": "a", "adventure": {}})
    )
    assert any("unknown people for the hero" in issue for issue in played)


def _member(name: str, character: UUID | None) -> PartyMember:
    return PartyMember(
        id=uuid4(),
        world_id=uuid4(),
        name=name,
        name_key=name.lower(),
        character_id=character,
        sheet=_ash(),
    )


def test_without_a_played_hero_nobody_chooses_and_every_member_leads() -> None:
    wren_id, ash_id, bram_id = uuid4(), uuid4(), uuid4()
    roster = [_member("Wren", wren_id), _member("Ash", ash_id), _member("Bram", bram_id)]
    assert chooser_keys(roster, None) == set()
    assert chooser_keys(roster, wren_id) == {"wren"}
    places = {str(wren_id): "hearth", str(ash_id): "hearth", str(bram_id): "market"}
    # Ash's own scene at the hearth: Wren stands there too; Bram is away.
    assert present_keys(roster, set(), {str(ash_id)}, places) == {"ash", "wren"}
    assert present_keys(roster, set(), {str(bram_id)}, places) == {"bram"}
    assert present_keys(roster, set(), {str(uuid4())}, places) == set()


def test_a_watched_party_member_keeps_the_party_in_mind() -> None:
    quiet = party_note(["Ash", "Bram"], [])
    assert quiet.startswith("You travel with Ash and Bram as an adventuring party")
    assert "fight is on" not in quiet
    goblin = Monster(
        id=uuid4(),
        world_id=uuid4(),
        name_key="goblin",
        name="Goblin",
        hp_current=7,
        hp_max=7,
        ac=15,
    )
    fight = party_note(["Ash"], [goblin])
    assert "A fight is on with Goblin (unhurt)" in fight and "Never spar" in fight
    assert party_note([], []) == "You are an adventurer seeking adventure."

    # Someone leads: the leader decides, the others go along (watched-party-001:
    # told only to keep together, both waited nine turns running).
    leads = party_note(["Ash"], [], "Wren", leads=True)
    assert leads.startswith("You lead an adventuring party (Ash with you)")
    assert "Decide and act" in leads
    follows = party_note(["Wren"], [], "Wren")
    assert "that Wren leads" in follows and "go where Wren goes" in follows


def test_the_party_goes_where_its_leader_goes() -> None:
    from worldsim.application.orchestration.stage1 import SealedPhase, follow_leader
    from worldsim.domain.commands import MoveAction, WaitAction
    from worldsim.domain.scenes import Intent

    world, snap = uuid4(), uuid4()
    wren, ash, sera = uuid4(), uuid4(), uuid4()
    hearth, market = uuid4(), uuid4()
    sealed = SealedPhase(snap, {}, {wren: hearth, ash: hearth, sera: market})

    def intent(who: UUID, action: Any, key: str = "s1char:x") -> Intent:
        return Intent(
            id=uuid4(),
            world_id=world,
            snapshot_id=snap,
            phase_run_id=uuid4(),
            author_character_id=who,
            idempotency_key=key,
            action=action,
        )

    go = MoveAction(character_id=wren, snapshot_id=snap, destination_location_id=market)
    intents = [
        intent(wren, go),
        intent(ash, WaitAction(character_id=ash, snapshot_id=snap)),
        intent(sera, WaitAction(character_id=sera, snapshot_id=snap)),
    ]
    led = follow_leader(intents, wren, sealed)
    assert isinstance(led[1].action, MoveAction)
    assert (led[1].action.character_id, led[1].action.destination_location_id) == (ash, market)
    assert isinstance(led[2].action, WaitAction)  # not standing with the leader
    assert follow_leader(intents, None, sealed) == intents
    directed = [intents[0], intent(ash, intents[1].action, "direct:abc")]
    assert follow_leader(directed, wren, sealed)[1].action == intents[1].action


def _roster(client: ApiClient, world_id: UUID) -> list[dict[str, Any]]:
    return client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=WATCHER
    ).json()["members"]


def _cast(client: ApiClient, world_id: UUID) -> dict[str, str]:
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=WATCHER
    ).json()["cast"]
    return {c["name"]: c["character_id"] for c in cast}


def test_a_watched_adventure_seats_the_cast_as_a_linked_party(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = wired
    created = _create(client, WATCHED, "watched-party")
    assert created.status_code == 200, created.text
    assert created.json()["character_id"] is None
    world_id = UUID(created.json()["world_id"])
    members = _roster(client, world_id)
    ids = _cast(client, world_id)
    assert sorted(m["name"] for m in members) == ["Ash", "Wren"]
    for m in members:
        assert m["character_id"] == ids[m["name"]] and m["level"] == 1
        assert m["race"] and m["character_class"] and m["hp_current"] == m["hp_max"] > 0
        # Nobody plays them, so nobody but the storyteller changes them.
        assert m["calling_changeable"] is False


class _Writer:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.prompts: list[str] = []

    async def write(self, prompt: str) -> Written:
        self.prompts.append(prompt)
        return Written(
            text=self.answers[len(self.prompts) - 1], model="fake", seconds=0.1, cost_usd=0.0
        )


def test_the_writer_may_give_the_watched_party_its_callings(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = wired
    created = _create(client, WATCHED, "watched-callings")
    world_id = UUID(created.json()["world_id"])
    writer = _Writer(['{"race": "elf", "class": "wizard"}', "no idea"])

    async def suggest() -> int:
        engine = create_engine(Settings())
        try:
            return await suggest_party_callings(
                lambda: create_unit_of_work(engine), writer, world_id
            )
        finally:
            await engine.dispose()

    before = {m["name"]: m["character_class"] for m in _roster(client, world_id)}
    assert asyncio.run(suggest()) == 1
    after = {m["name"]: (m["race"], m["character_class"]) for m in _roster(client, world_id)}
    # The roster reads by name: Ash is asked first.
    assert after["Ash"] == ("elf", "wizard")
    assert after["Wren"][1] == before["Wren"]  # an unusable answer keeps the card's calling
    # The second member is asked knowing the first one's new calling.
    assert "Ash (elf wizard)" in writer.prompts[1]


def test_a_watched_party_takes_the_first_four_of_the_cast(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, _ = wired
    names = ["Wren", "Ash", "Lyra", "Bram", "Tess"]
    draft = client.post(
        "/api/v1/story-drafts",
        json={
            "payload": {
                "world": {
                    "preset_id": "20000000-0000-4000-8000-000000000001",
                    "preset_revision": 2,
                },
                "cast": [
                    {
                        "instance_key": f"cast-{n.lower()}",
                        "preset_id": "20000000-0000-4000-8000-000000000101",
                        "preset_revision": 1,
                        "name": n,
                    }
                    for n in names
                ],
                "mode": WATCHED,
                "story": {"title": "Five at the Hearth"},
                "ai": {"art_source": "curated"},
            },
            "current_step": "review",
        },
    )
    assert draft.status_code == 200, draft.text
    created = client.post(
        "/api/v1/stories",
        json={"draft_id": draft.json()["id"], "expected_draft_version": 1},
        headers={"Idempotency-Key": "watched-five"},
    )
    assert created.status_code == 200, created.text
    members = _roster(client, UUID(created.json()["world_id"]))
    assert sorted(m["name"] for m in members) == sorted(names[:4])


def test_a_watched_party_fights_together(wired: tuple[ApiClient, FakeGateway]) -> None:
    client, gateway = wired
    created = _create(client, WATCHED, "watched-fight", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    ids = _cast(client, world_id)
    turn = {"n": 0}
    noted: list[str] = []

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if turn["n"] == 1 and "Hearth" in prompt:
                # A zombie: hardy, so the fight is still on next turn.
                text = "ENCOUNTER[zombie]: A zombie lurches through the door."
                return json.dumps([{"text": text, "cited_fact_keys": ["dnd-sheet:wren"]}])
            return None
        if "as an adventuring party" in prompt:
            noted.append(prompt)
        who = ids["Wren"]  # the server pins the real character
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index in (1, 2):
        turn["n"] = index
        moved = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(world_id), "absolute_index": index},
            headers=WATCHER,
        )
        assert moved.status_code == 200, moved.text
        if index == 1:
            _heal_all(world_id)
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=WATCHER,
    ).json()["entries"]
    rolls = [r for e in entries if e["combat"] for r in e["combat"]["rolls"]]
    first = next(e["combat"] for e in entries if e["combat"])
    # Nobody played acted, yet both members at the hearth struck the zombie.
    swung = {
        r.get("actor") for r in first["rolls"] if r["kind"] == "attack" and not r.get("actor_foe")
    }
    assert swung == {"Wren", "Ash"}, first["rolls"]
    assert any(r["kind"] == "encounter" for r in rolls)
    assert not any(r.get("choose") for r in rolls)
    # Each member hears they travel as a party, and with the fight on their
    # own waiting became a blow.
    assert noted
    assert "interact" in _families(world_id)


def test_a_quiet_watched_party_is_brought_trouble(wired: tuple[ApiClient, FakeGateway]) -> None:
    from worldsim.domain.party import TROUBLE_AFTER

    client, gateway = wired
    created = _create(client, WATCHED, "watched-quiet", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    ids = _cast(client, world_id)
    told: dict[int, bool] = {}
    turn = {"n": 0}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            told[turn["n"]] = told.get(turn["n"], False) or "out for adventure" in prompt
            return None
        who = ids["Wren"]
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Fine."})
        return None

    gateway.route = route
    for index in range(1, TROUBLE_AFTER + 1):
        turn["n"] = index
        moved = client.post(
            "/api/v1/stage1/advance",
            json={"world_id": str(world_id), "absolute_index": index},
            headers=WATCHER,
        )
        assert moved.status_code == 200, moved.text
    # Watched-party-001: no foes came in 14 turns until the storyteller was
    # told it may bring them, once the party has gone a while without.
    assert told[TROUBLE_AFTER] and not any(told[n] for n in range(1, TROUBLE_AFTER))
    # The storyteller here writes no tag at all, and the fight opens anyway.
    entries = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 80},
        headers=WATCHER,
    ).json()["entries"]
    opened = [
        (e["absolute_index"], r["text"])
        for e in entries
        if e["combat"]
        for r in e["combat"]["rolls"]
        if r["kind"] == "encounter"
    ]
    assert [index for index, _text in opened] == [TROUBLE_AFTER], opened
