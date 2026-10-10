"""Ability checks outside fights (combat-depth-003).

- A party member's uncertain attempt that is no blow rolls the skill its
  words call for, against a difficulty its words set.
- The resolver hears the roll and the outcome follows it: a find or a
  settled rumour needs a success; the resolver may still hold it lower.
- The rolls are kept beside the scene as its dice.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.application.orchestration.stage1 import follow_checks, roll_checks
from worldsim.domain.commands import InteractAction
from worldsim.domain.effects import ItemFoundEffect
from worldsim.domain.enums import ResolutionOutcome, ResolverKind
from worldsim.domain.ids import new_character_id, new_party_member_id, new_world_id
from worldsim.domain.party import PartyMember
from worldsim.domain.rules.dnd import HitPoints, Sheet
from worldsim.domain.rules.dnd.checks import (
    Check,
    check_line,
    dc_for,
    roll_check,
    scene_outcome,
    skill_for,
)
from worldsim.domain.scenes import Intent, Resolution
from worldsim.infrastructure.model_gateway.fake import FakeGateway


def _rogue() -> Sheet:
    return Sheet(
        name="Wren",
        race="human",
        character_class="rogue",
        level=1,
        stats={"str": 10, "dex": 16, "con": 12, "int": 12, "wis": 10, "cha": 14},
        hp=HitPoints(current=9, max=9),
        weapons=["dagger"],
    )


def _die(natural: int) -> Any:
    return lambda: (natural - 1) / 20


def _check(outcome: str) -> Check:
    return Check("Wren", "Athletics", "str", 12, 10, 0, 10, outcome)


def test_the_words_name_the_skill_and_how_hard_it_is() -> None:
    assert skill_for("I pick the lock on the chest") == ("Thieves' tools", "dex")
    assert skill_for("I sneak past the guard") == ("Stealth", "dex")
    assert skill_for("I climb the wall") == ("Athletics", "str")
    assert skill_for("I try to persuade the gatekeeper") == ("Persuasion", "cha")
    assert skill_for("I search the cellar for the key") == ("Perception", "wis")
    assert skill_for("I say hello") is None
    assert dc_for("I climb the sheer cliff") == 15
    assert dc_for("I climb the low fence") == 10
    assert dc_for("I climb the wall") == 12


def test_the_roll_decides_success_partial_or_failure() -> None:
    rogue = _rogue()  # dex +3
    made = roll_check(rogue, "I sneak past the guard", _die(9))
    assert made is not None and (made.total, made.dc, made.outcome) == (12, 12, "success")
    close = roll_check(rogue, "I sneak past the guard", _die(5))
    assert close is not None and (close.total, close.outcome) == (8, "partial")
    missed = roll_check(rogue, "I sneak past the guard", _die(2))
    assert missed is not None and missed.outcome == "failure"
    # A natural 20 always succeeds and a natural 1 always fails.
    hard = roll_check(rogue, "I climb the sheer cliff", _die(20))  # str +0, DC 15
    assert hard is not None and hard.outcome == "success"
    fumble = roll_check(rogue, "I climb the low fence", _die(1))
    assert fumble is not None and fumble.outcome == "failure"
    assert "outcome follows the roll: success" in check_line(made)


def test_the_best_roll_decides_and_the_resolver_may_hold_it_lower() -> None:
    assert scene_outcome("success", [_check("failure"), _check("partial")]) == "partial"
    assert scene_outcome("failure", [_check("success")]) == "failure"
    assert scene_outcome("impossible", [_check("success")]) == "impossible"
    assert scene_outcome("partial", []) == "partial"


def test_only_a_party_members_uncertain_attempt_rolls() -> None:
    world, scene = new_world_id(), uuid4()
    wren, ash = new_character_id(), new_character_id()
    roster = [
        PartyMember(
            id=new_party_member_id(),
            world_id=world,
            name="Wren",
            name_key="wren",
            character_id=wren,
            sheet=_rogue(),
        )
    ]

    def attempt(who: UUID, words: str) -> Intent:
        return Intent(
            id=uuid4(),
            world_id=world,
            snapshot_id=uuid4(),
            phase_run_id=uuid4(),
            author_character_id=who,
            idempotency_key=words,
            action=InteractAction(character_id=who, snapshot_id=uuid4(), attempt=words),
        )

    members = [
        attempt(wren, "I pick the lock"),
        attempt(wren, "I stab the goblin with my dagger"),  # the fight's dice
        attempt(ash, "I climb the wall"),  # no sheet
    ]
    checks = roll_checks(scene, members, roster)
    assert [(c.actor, c.skill) for c in checks] == [("Wren", "Thieves' tools")]
    # Seeded by scene and attempt: a redone scene rolls the same.
    assert roll_checks(scene, members, roster) == checks


def test_a_failed_check_takes_the_find_away() -> None:
    wren = uuid4()
    found = ItemFoundEffect(
        affected_ids=[wren],
        expected_versions={str(wren): 1},
        owner_character_id=wren,
        name="Iron key",
    )
    resolution = Resolution(
        id=uuid4(),
        world_id=uuid4(),
        scene_id=uuid4(),
        outcome=ResolutionOutcome.SUCCESS,
        resolver=ResolverKind.MODEL,
        effects=[found],
        rationale="The lock gives.",
    )
    failed = follow_checks(resolution, [_check("failure")])
    assert failed.outcome == ResolutionOutcome.FAILURE and failed.effects == []
    assert failed.rationale.startswith("Wren's Athletics check: 10 against DC 12, failure.")
    made = follow_checks(resolution, [_check("success")])
    assert made.outcome == ResolutionOutcome.SUCCESS and made.effects == [found]
    assert follow_checks(resolution, []) is resolution


def test_a_heros_climb_is_rolled_told_and_kept_beside_the_scene(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "check-story")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    told: list[str] = []

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            return None
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": wren, "snapshot_id": wren})
        if "You resolve" in system:
            told.append(prompt)
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Up she goes."})
        return None

    gateway.route = route
    moved = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 1,
            "player_intents": {
                wren: {
                    "family": "interact",
                    "character_id": wren,
                    "snapshot_id": NIL_SNAPSHOT,
                    "attempt": "I climb the steep wall of the old granary",
                }
            },
        },
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert any("Dice: Wren's Athletics check:" in prompt for prompt in told)
    chronicle = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 50},
        headers=headers,
    ).json()
    (dice,) = [e["combat"] for e in chronicle["entries"] if e["combat"]]
    (roll,) = dice["rolls"]
    assert (roll["kind"], roll["actor"], roll["using"], roll["dc"]) == (
        "check",
        "Wren",
        "Athletics",
        15,
    )
    assert roll["result"] in {"success", "partial", "failure"}
    party = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()
    strength = party["members"][0]["abilities"]["str"]
    assert roll["roll"] == roll["natural"] + (strength - 10) // 2
    assert dice["scene_event_id"]
