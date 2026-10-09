"""A joining companion's calling is suggested, and the player may change it (callings-001)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from test_party_combat import FIGHTER, NIL_SNAPSHOT, _create
from test_party_combat import wired as wired
from test_stage1_api import ApiClient

from worldsim.application.callings import calling_prompt, parse_calling, suggest_calling
from worldsim.application.ports.writer import WritingError, Written
from worldsim.domain.characters import CharacterCard
from worldsim.domain.ids import (
    CharacterId,
    new_card_id,
    new_character_id,
    new_party_member_id,
    new_world_id,
)
from worldsim.domain.party import PartyMember
from worldsim.domain.rules.dnd import HitPoints, Sheet, auto_sheet, load_data
from worldsim.domain.rules.dnd.callings import calling_changeable, has_fought, rebuild_calling
from worldsim.domain.rules.dnd.invites import companion_description
from worldsim.infrastructure.model_gateway.fake import FakeGateway

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")

ASH_CARD = CharacterCard(
    id=new_card_id(),
    character_id=new_character_id(),
    name="Ash",
    appearance="Steady stance, weather-worn cloak.",
    personality="Patient, dry-witted, dependable.",
    background="Market ward born and bred.",
    pronouns="he/him",
)


class _Writer:
    """A stand-in writing model: one fixed answer, and the prompts it read."""

    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    async def write(self, prompt: str) -> Written:
        self.prompts.append(prompt)
        if self.answer is None:
            raise WritingError("writer unreachable")
        return Written(text=self.answer, model="fake/writer", seconds=0.1, cost_usd=0.0001)


def _member(name: str, sheet: Sheet, character: CharacterId | None = None) -> PartyMember:
    return PartyMember(
        id=new_party_member_id(),
        world_id=new_world_id(),
        name=name,
        name_key=name.lower(),
        character_id=character,
        sheet=sheet,
    )


def test_the_writer_answer_is_read_against_the_tables() -> None:
    assert parse_calling('{"race": "elf", "class": "cleric"}', DATA) is not None
    said = parse_calling('Sure! ```json\n{"race": "Half Elf", "class": "Ranger"}\n```', DATA)
    assert said is not None and said.description == "half-elf ranger"
    assert parse_calling('{"race": "centaur", "class": "cleric"}', DATA) is None
    assert parse_calling('{"race": "elf", "class": "necromancer"}', DATA) is None
    assert parse_calling("a cleric, I think", DATA) is None
    assert parse_calling('["elf", "cleric"]', DATA) is None


def test_the_prompt_names_the_party_and_the_card() -> None:
    wren = _member("Wren", auto_sheet("Wren", "human", "fighter", 1, DATA))
    prompt = calling_prompt(ASH_CARD, [wren], DATA)
    assert "Wren (human fighter)" in prompt
    assert "Ash (he/him)" in prompt and "Market ward born and bred." in prompt
    assert "half-orc" in prompt and "warlock" in prompt
    assert "nobody yet" in calling_prompt(ASH_CARD, [], DATA)


def test_a_suggestion_falls_back_to_the_card_words() -> None:
    wren = _member("Wren", auto_sheet("Wren", "human", "fighter", 1, DATA))
    chosen = _Writer('{"race": "human", "class": "ranger"}')
    assert asyncio.run(suggest_calling(chosen, ASH_CARD, [wren], DATA)) == "human ranger"
    assert len(chosen.prompts) == 1
    # No writer, a failed call or an answer outside the tables: the keywords.
    for writer in (None, _Writer(None), _Writer('{"race": "orc", "class": "ninja"}')):
        assert asyncio.run(suggest_calling(writer, ASH_CARD, [wren], DATA)) == "human fighter"
    assert companion_description("a half-elf minstrel", DATA) == "half-elf bard"


def test_fighting_is_read_from_the_kept_dice() -> None:
    joined = {"rolls": json.dumps([{"kind": "recruit", "actor": "Ash"}])}
    settled = {"rolls": json.dumps([{"kind": "xp", "actor": ["Wren", "Ash"], "share": 50}])}
    struck = {"rolls": json.dumps([{"kind": "attack", "actor": "Goblin", "target": "Ash"}])}
    swung = {"rolls": json.dumps([{"kind": "attack", "actor": "ash", "target": "Goblin"}])}
    assert not has_fought("Ash", [joined, settled, {"rolls": "not json"}, {}])
    assert has_fought("Ash", [joined, struck]) and has_fought("Ash", [swung])
    assert not has_fought("Wren", [struck])

    hero_id = new_character_id()
    hero = _member("Wren", auto_sheet("Wren", "human", "fighter", 1, DATA), hero_id)
    ash = _member("Ash", auto_sheet("Ash", "human", "fighter", 1, DATA), new_character_id())
    assert calling_changeable(ash, hero_id, fought=False, fight_on=False)
    assert not calling_changeable(hero, hero_id, fought=False, fight_on=False)
    assert not calling_changeable(ash, hero_id, fought=True, fight_on=False)
    assert not calling_changeable(ash, hero_id, fought=False, fight_on=True)
    assert not calling_changeable(ash, None, fought=False, fight_on=False)


def test_a_new_calling_keeps_name_level_and_experience() -> None:
    old = auto_sheet("Ash", "human", "fighter", 3, DATA).model_copy(
        update={"xp": 1000, "rest_day": 2}
    )
    new = rebuild_calling(old, "elf", "cleric", DATA)
    assert (new.name, new.level, new.xp, new.rest_day) == ("Ash", 3, 1000, 2)
    assert (new.race, new.character_class) == ("elf", "cleric") and new.spells
    assert new.hp is not None and new.hp.current == new.hp.max
    assert isinstance(new.hp, HitPoints)


def _advance(client: ApiClient, world_id: UUID, index: int, wren: str, intent: Any) -> None:
    moved = client.post(
        "/api/v1/stage1/advance",
        json={
            "world_id": str(world_id),
            "absolute_index": index,
            "player_intents": {wren: intent},
        },
        headers={"X-Worldsim-Role": "player", "X-Worldsim-Character": wren},
    )
    assert moved.status_code == 200, moved.text


def test_a_companion_joins_with_a_suggested_calling_and_may_change_it_until_they_fight(
    wired: tuple[ApiClient, FakeGateway],
) -> None:
    client, gateway = wired
    writer = _Writer('{"race": "human", "class": "cleric"}')
    client._raw_any().app.state.app_state._writer = writer  # pyright: ignore[reportPrivateUsage]
    created = _create(client, FIGHTER, "calling-story", ash_at="hearth")
    assert created.status_code == 200, created.text
    world_id = UUID(created.json()["world_id"])
    wren = created.json()["character_id"]
    headers = {"X-Worldsim-Role": "player", "X-Worldsim-Character": wren}
    cast = client.get(
        "/api/v1/world/presentation", params={"world_id": str(world_id)}, headers=headers
    ).json()["cast"]
    ash = next(c["character_id"] for c in cast if c["name"] == "Ash")
    fight = False

    def route(request: Any) -> str | None:
        system, prompt = request.system or "", request.prompt
        if "You narrate" in system:
            if not fight or "Hearth" not in prompt:
                return None
            text = "ENCOUNTER[goblin]: A goblin leaps out.\nATTACK[goblin at Ash]: It slashes."
            return json.dumps([{"text": text, "cited_fact_keys": ["dnd-sheet:wren"]}])
        if "You react" in system and "join their party" in prompt:
            return json.dumps(
                {
                    "family": "communicate",
                    "character_id": ash,
                    "snapshot_id": ash,
                    "target_character_id": wren,
                    "topic": "Yes, I will come with you.",
                }
            )
        who = wren if "You decide" in system and "Wren" in prompt else ash
        if "You decide" in system or "You react" in system:
            return json.dumps({"family": "wait", "character_id": who, "snapshot_id": who})
        if "You resolve" in system:
            return json.dumps({"outcome": "success", "effects": [], "rationale": "Agreed."})
        return None

    gateway.route = route
    _advance(
        client,
        world_id,
        1,
        wren,
        {
            "family": "communicate",
            "character_id": wren,
            "snapshot_id": NIL_SNAPSHOT,
            "target_character_id": ash,
            "topic": "Ash, will you join me as my companion on the road?",
        },
    )
    assert writer.prompts and "Wren (human fighter)" in writer.prompts[0]

    def roster() -> dict[str, Any]:
        party = client.get(
            "/api/v1/stage1/party", params={"world_id": str(world_id)}, headers=headers
        ).json()
        return {m["name"]: m for m in party["members"]}

    members = roster()
    assert (members["Ash"]["race"], members["Ash"]["character_class"]) == ("human", "cleric")
    assert members["Ash"]["calling_changeable"] and not members["Wren"]["calling_changeable"]

    def change(name: str, race: str, cls: str, who: dict[str, str], version: int | None = None):
        member = roster()[name]
        return client.post(
            f"/api/v1/stage1/party/{member['id']}/calling",
            json={
                "world_id": str(world_id),
                "race": race,
                "character_class": cls,
                "expected_version": member["version"] if version is None else version,
            },
            headers=who,
        )

    assert change("Wren", "elf", "wizard", headers).status_code == 409
    assert change("Ash", "centaur", "ranger", headers).status_code == 422
    stale = roster()["Ash"]["version"] + 5
    assert change("Ash", "elf", "ranger", headers, stale).status_code == 409
    changed = change("Ash", "elf", "ranger", headers)
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["name"], body["race"], body["character_class"], body["level"]) == (
        "Ash",
        "elf",
        "ranger",
        1,
    )
    assert body["calling_changeable"] and body["hp_current"] == body["hp_max"]
    assert roster()["Ash"]["character_class"] == "ranger"

    # In a Director seat (no played character in the grant) the hero is the
    # one the story was created for: Ash may change, Wren may not.
    def seat(role: str, character: str | None = None) -> None:
        chosen = client.post(
            "/api/v1/stage2/roles/select",
            json={"world_id": str(world_id), "role": role, "character_id": character},
        )
        assert chosen.status_code == 200, chosen.text

    seat("director")
    director = {"X-Worldsim-Role": "director"}
    assert roster()["Ash"]["calling_changeable"] and not roster()["Wren"]["calling_changeable"]
    assert change("Wren", "elf", "wizard", director).status_code == 409
    assert change("Ash", "halfling", "rogue", director).status_code == 200
    seat("player", wren)

    # A goblin strikes Ash: from then on the calling stays.
    fight = True
    _advance(
        client,
        world_id,
        2,
        wren,
        {"family": "wait", "character_id": wren, "snapshot_id": NIL_SNAPSHOT},
    )
    assert not roster()["Ash"]["calling_changeable"]
    refused = change("Ash", "dwarf", "cleric", headers)
    assert refused.status_code == 409 and "fought" in refused.text
