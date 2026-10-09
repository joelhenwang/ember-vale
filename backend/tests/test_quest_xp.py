"""A settled rumour gives a combat story's party experience (quest-xp-001).

- Each member gains the 5e medium-encounter XP for their own level, in full.
- Levels follow as for fights; only linked heroes are left choices.
- Both ways a rumour settles (the director's ending, the resolver's
  ``hook_settled``) award it once, under the scene where it settled.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.application.orchestration.settle_xp import award_settled_hooks
from worldsim.domain.enums import NarrativeStatus
from worldsim.domain.narrative import NarrativeHook
from worldsim.domain.rules.dnd import HitPoints, Sheet, load_data
from worldsim.domain.rules.dnd.quests import award_settled, settle_xp
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")


def _sheet(name: str, level: int = 1, xp: int = 0, hp: int = 12, cls: str = "fighter") -> Sheet:
    return Sheet(
        name=name,
        race="human",
        character_class=cls,
        level=level,
        xp=xp,
        stats={"str": 16, "dex": 13, "con": 14, "int": 8, "wis": 12, "cha": 10},
        hp=HitPoints(current=hp, max=12),
        weapons=["longsword"],
    )


def test_settle_xp_is_the_medium_encounter_threshold() -> None:
    assert [settle_xp(level) for level in (1, 2, 3, 4, 5, 10, 20)] == [
        50,
        100,
        150,
        250,
        500,
        1200,
        5700,
    ]
    assert settle_xp(0) == 50 and settle_xp(25) == settle_xp(20)


def test_each_member_gets_it_in_full_and_the_inputs_stay() -> None:
    wren, lyra = _sheet("Wren"), _sheet("Lyra")
    award = award_settled(DATA, "The missing flour", [("wren", wren), ("lyra", lyra)])
    assert {key: s.xp for key, s in award.sheets.items()} == {"wren": 50, "lyra": 50}
    assert wren.xp == 0 and lyra.xp == 0
    (row,) = award.rolls
    assert row == {
        "kind": "xp",
        "result": "settled",
        "text": "Settled: The missing flour · 50 XP each.",
        "target": "The missing flour",
        "amount": 100,
        "share": 50,
    }


def test_members_of_different_levels_are_named_by_amount() -> None:
    award = award_settled(
        DATA, "The stuck cart", [("wren", _sheet("Wren")), ("elara", _sheet("Elara", 3, 900))]
    )
    assert [(r["actor"], r["share"]) for r in award.rolls] == [("Wren", 50), ("Elara", 150)]
    assert award.sheets["elara"].xp == 1050


def test_crossing_a_threshold_levels_up_and_only_heroes_choose() -> None:
    hero, friend = _sheet("Wren", 3, 2600), _sheet("Ash", 3, 2600)
    award = award_settled(
        DATA, "The bandit toll", [("wren", hero), ("ash", friend)], chooses={"wren"}
    )
    assert award.sheets["wren"].level == 4 and award.sheets["ash"].level == 4
    levels = [r for r in award.rolls if r["kind"] == "level"]
    assert [(r["actor"], r["level"]) for r in levels] == [("Wren", 4), ("Ash", 4)]
    # Level 4 brings an Ability Score Improvement: the hero chooses, Ash takes it.
    assert levels[0].get("choose") == "ability" and "choose" not in levels[1]
    assert award.sheets["wren"].choices and not award.sheets["ash"].choices


def test_a_downed_hero_stays_down_but_still_learns() -> None:
    award = award_settled(DATA, "The well", [("wren", _sheet("Wren", 1, 280, hp=0))])
    woke = award.sheets["wren"]
    assert woke.level == 2 and woke.hp is not None and woke.hp.current == 0


def test_no_party_no_award() -> None:
    assert award_settled(DATA, "Anything", []).rolls == []


# --- end to end ------------------------------------------------------------


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _add_hooks(world: UUID, *titles: str, people: tuple[UUID, ...] = ()) -> list[UUID]:
    engine = create_engine(Settings())
    ids = [uuid.uuid4() for _ in titles]
    try:
        async with create_unit_of_work(engine) as uow:
            for hook_id, title in zip(ids, titles, strict=True):
                await uow.narrative.add_hook(
                    NarrativeHook(
                        id=hook_id,
                        world_id=world,
                        title=title,
                        purpose=f"{title}: a matter in the vale.",
                        status=NarrativeStatus.ACTIVE,
                        participant_ids=list(people),
                    )
                )
            await uow.commit()
    finally:
        await engine.dispose()
    return ids


async def _award_again(world: UUID, hooks: list[UUID]) -> list[UUID]:
    engine = create_engine(Settings())
    try:
        return await award_settled_hooks(
            lambda: create_unit_of_work(engine),
            lambda: DATA,
            world,
            hooks,
            absolute_index=1,
            run_id=None,
        )
    finally:
        await engine.dispose()


def test_both_ways_of_settling_give_the_party_xp_once(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    created = _create(client, FIGHTER, "quest-xp")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cart, flour = _run(
        _add_hooks(world_id, "The stuck cart", "The missing flour", people=(UUID(wren),))
    )
    # A rumour among others only, settled by the director: the party took no
    # part in it, so it pays nothing.
    (quarrel,) = _run(_add_hooks(world_id, "The baker's quarrel"))
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ids = {c["name"]: c["character_id"] for c in cast}

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You direct" in system:
            return json.dumps(
                {
                    "action": "noop",
                    "reason": "story is moving",
                    "resolved": [
                        {"hook_id": str(flour), "ending": "The flour was found."},
                        {"hook_id": str(quarrel), "ending": "The bakers made peace."},
                    ],
                }
            )
        if "You resolve" in system and "heave the wheel" in prompt:
            return json.dumps(
                {
                    "outcome": "success",
                    "rationale": "Wren has the leverage.",
                    "effects": [
                        {
                            "effect_type": "hook_settled",
                            "affected_ids": [wren],
                            "hook_id": str(cart),
                            "ending": "The cart rolls free.",
                        }
                    ],
                }
            )
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Waiting."})
        who = ids["Wren"] if "Wren" in prompt else ids["Ash"]
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        return None

    gateway.route = route
    advanced = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": 1,
            "player_intents": {
                wren: {
                    "family": "interact",
                    "character_id": wren,
                    "snapshot_id": NIL_SNAPSHOT,
                    "attempt": "heave the wheel out of the mud",
                }
            },
        },
        headers=headers,
    )
    assert advanced.status_code == 200, advanced.text

    (hero,) = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()["members"]
    assert hero["xp"] == 100 and hero["level"] == 1

    chronicle = client.get(
        "/api/v1/world/chronicle",
        params={"world_id": str(world_id), "after": 0, "limit": 50},
        headers=headers,
    ).json()["entries"]
    logs = [e["combat"] for e in chronicle if e["combat"]]
    settled = {r["target"]: log for log in logs for r in log["rolls"] if r["kind"] == "xp"}
    assert set(settled) == {"The stuck cart", "The missing flour"}
    for log in settled.values():
        (row,) = log["rolls"]
        assert (row["result"], row["share"]) == ("settled", 50)
    # The resolver's settle sits under the scene that did it.
    scene = next(
        e for e in chronicle if e["event_id"] == settled["The stuck cart"]["scene_event_id"]
    )
    assert scene["scene_id"] is not None
    assert settled["The missing flour"]["scene_event_id"] is None

    # A replayed settle finds its event and gives nothing twice.
    assert _run(_award_again(world_id, [cart, flour])) == []
    (again,) = client.get(
        "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
    ).json()["members"]
    assert again["xp"] == 100
