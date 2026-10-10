"""D&D party roster contracts (owned by DND-WIRE).

One row per adventurer per world: the player's sheet plus recruited
companions. ``name_key`` is the slugified name and carries the
uniqueness that makes repeat RECRUIT tags idempotent. Sheet HP and
slots mutate through version-guarded saves; joins are inserts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import FocusSlot
from worldsim.domain.ids import CharacterId, MonsterId, PartyMemberId, WorldId
from worldsim.domain.rules.dnd import DataTables, Sheet, slugify
from worldsim.domain.rules.dnd.progress import slots_left


class PartyMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PartyMemberId
    world_id: WorldId
    name: str = Field(min_length=1, max_length=128)
    name_key: str = Field(min_length=1, max_length=128)
    character_id: CharacterId | None = None
    focus_slot: FocusSlot = FocusSlot.COMPANION
    sheet: Sheet
    version: int = Field(default=0, ge=0)


def party_in_scene(roster: list[PartyMember], participants: list[str]) -> list[PartyMember]:
    """The roster when the party is in this scene, else nobody.

    The party travels with its linked hero, so a scene without them has no
    party. A roster with no linked member at all (a party begun by hand)
    counts everywhere, as before.
    """
    linked = [m for m in roster if m.character_id is not None]
    if not linked or any(str(m.character_id) in participants for m in linked):
        return roster
    return []


def party_name_key(name: str) -> str:
    """Dedupe key for member names (monolith compares lowercased names)."""
    return slugify(name)


class Monster(BaseModel):
    """One persistent monster pool per world and name key.

    Narrator tags address monsters by name only, so one row tracks the
    live pool for a key. A new ENCOUNTER respawns the key to full: a
    fresh pack, not the survivors of the last fight.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: MonsterId
    world_id: WorldId
    name_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    hp_current: int = Field(ge=0)
    hp_max: int = Field(ge=0)
    ac: int = Field(ge=0)
    version: int = Field(default=0, ge=0)


#: World config: the orders the hero gave companions in the fight that is on.
PARTY_ORDERS_KEY = "party_orders"

#: A fight stays "on" this many turns after its last roll.
FIGHT_LINGERS = 2


def fight_keys(summary: dict[str, str]) -> list[str]:
    """The foes a fight event names (its ``foes`` summary, JSON)."""
    try:
        raw: object = json.loads(summary.get("foes", "[]"))
    except ValueError:
        return []
    return [str(key) for key in cast("list[object]", raw)] if isinstance(raw, list) else []


def foes_on(fight_index: int, now: int, keys: list[str], pools: list[Monster]) -> list[Monster]:
    """The latest fight's foes while it is on: recent, and someone standing."""
    if now - fight_index > FIGHT_LINGERS:
        return []
    by_key = {pool.name_key: pool for pool in pools}
    foes = [by_key[key] for key in keys if key in by_key]
    return foes if any(foe.hp_current > 0 for foe in foes) else []


def _shape(foe: Monster) -> str:
    if foe.hp_current <= 0:
        return "down"
    share = foe.hp_current / foe.hp_max if foe.hp_max else 1
    if share > 0.99:
        return "unhurt"
    return "wounded" if share > 0.5 else "badly wounded"


def foes_line(foes: list[Monster]) -> str:
    """The fight that is on, for the narrator: in words, never numbers."""
    shown = ", ".join(f"{foe.name} ({_shape(foe)})" for foe in foes)
    return (
        f"A fight is on with: {shown}. Do not ENCOUNTER them again (that would bring "
        "fresh ones); strike them by name, and let those still standing strike back. "
        "The down stay down."
    )


_SLOT_WORDS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")


def slots_line(tables: DataTables, sheet: Sheet, day: int | None) -> str:
    """The narrator's line of spell slots still free today ("" for non-casters),
    so it does not describe a spell the engine will refuse."""
    left = slots_left(tables, sheet, day)
    if not left:
        return ""
    shown = ", ".join(f"{n} {_SLOT_WORDS[pos]}-level" for pos, n in enumerate(left))
    return f"\nSpell slots left today: {shown} (cantrips are free)"


def fight_over_line(
    fight_index: int, now: int, keys: list[str], pools: list[Monster]
) -> str | None:
    """A fight that just ended (recent, every foe down), for the narrator: the
    slain kept appearing in later prose, growling from the corner."""
    if now - fight_index > FIGHT_LINGERS:
        return None
    by_key = {pool.name_key: pool for pool in pools}
    foes = [by_key[key] for key in keys if key in by_key]
    if not foes or any(foe.hp_current > 0 for foe in foes):
        return None
    shown = ", ".join(foe.name for foe in foes)
    lie = "lies" if len(foes) == 1 else "lie"
    return f"The fight is over: {shown} {lie} defeated. They do not rise, growl or strike again."


def down_line(names: list[str]) -> str | None:
    """Party members at 0 hit points, for the narrator: they cannot act."""
    if not names:
        return None
    who = ", ".join(names)
    verb = "is" if len(names) == 1 else "are"
    return (
        f"{who} {verb} down (no hit points left): conscious only enough to lie still, unable to "
        "fight or cast until healed or until a night's rest."
    )


def chooser_keys(roster: list[PartyMember], played: CharacterId | None) -> set[str]:
    """Who makes their own level-up choices: the played hero. A companion is
    linked to their own character too (companions-001) but does not choose.
    Without a played character (a watched party), nobody."""
    if played is None:
        # A watched party (no played character): nobody waits on a choice,
        # every level-up is made at once.
        return set()
    return {m.name_key for m in roster if m.character_id is not None and m.character_id == played}


def present_keys(
    roster: list[PartyMember],
    choosers: set[str],
    participants: set[str],
    places: Mapping[str, str],
) -> set[str]:
    """The party beside the played hero in this scene: empty unless the hero
    is in it. Linked companions count when they stand where the hero stands
    (a companion who only waits gets a scene of their own, and once struck
    alone there, ahead of the hero, companions-001); the unlinked travel
    with the hero. ``places`` maps linked characters to their location.
    Without a hero (a watched party, no ``choosers``), every linked member
    in the scene counts as one."""
    heroes = [m for m in roster if m.name_key in choosers and m.character_id is not None]
    if not heroes:
        # A watched party (no played hero): every linked member leads, and
        # the party is where any of them is in this scene.
        heroes = [m for m in roster if m.character_id is not None]
    here = [m for m in heroes if str(m.character_id) in participants]
    if not here:
        return set()
    spots = {places.get(str(m.character_id)) for m in here} - {None}
    return {
        m.name_key
        for m in roster
        if m.character_id is None
        or str(m.character_id) in participants
        or places.get(str(m.character_id)) in spots
    }


def party_took_part(roster: list[PartyMember], people: set[CharacterId]) -> bool:
    """A matter the party took part in: one of its linked members is among
    the people (a rumour's own, or the scene where it settled)."""
    return any(m.character_id is not None and m.character_id in people for m in roster)


def companion_note(hero: str, foes: list[Monster]) -> str:
    """What a companion keeps in mind (companions-001): they are in the party,
    and which fight is on. Without it Ash walked off to the market, waited or
    sparred the hero with goblins standing; only the fallback ever swung."""
    note = (
        f"You travel with {hero}'s party as their companion: you go where {hero} goes "
        f"and stand by them; your own errands wait while you travel together."
    )
    standing = [foe for foe in foes if foe.hp_current > 0]
    if standing:
        shown = ", ".join(f"{foe.name} ({_shape(foe)})" for foe in standing)
        note += (
            f" A fight is on with {shown}. Fight beside {hero}: attack one of them and "
            f'name it ("I swing at {standing[0].name}"). Never spar with your companions '
            "while foes stand."
        )
    return note


def party_note(fellows: list[str], foes: list[Monster]) -> str:
    """What a member of a watched party keeps in mind (no played hero): they
    travel together as an adventuring party seeking adventure, and which
    fight is on."""
    if fellows:
        together = ", ".join(fellows[:-1]) + (" and " if len(fellows) > 1 else "") + fellows[-1]
        note = (
            f"You travel with {together} as an adventuring party, seeking adventure: "
            "keep together, go where the party goes and face what comes as one."
        )
    else:
        note = "You are an adventurer seeking adventure."
    standing = [foe for foe in foes if foe.hp_current > 0]
    if standing:
        shown = ", ".join(f"{foe.name} ({_shape(foe)})" for foe in standing)
        note += (
            f" A fight is on with {shown}. Fight beside your party: attack one of them and "
            f'name it ("I swing at {standing[0].name}"). Never spar with your companions '
            "while foes stand."
        )
    return note


def stored_orders(raw: object, foes: list[str]) -> dict[str, str]:
    """The orders kept in the world config (``PARTY_ORDERS_KEY``), when the
    fight they were given in is still the one on (a foe key in common)."""
    if not isinstance(raw, dict):
        return {}
    record = cast("dict[str, object]", raw)
    given = record.get("foes")
    orders = record.get("orders")
    if not isinstance(given, list) or not isinstance(orders, dict):
        return {}
    if not {str(k) for k in cast("list[object]", given)} & set(foes):
        return {}
    return {str(k): str(v) for k, v in cast("dict[object, object]", orders).items()}


def orders_record(orders: dict[str, str], foes: list[str]) -> dict[str, object]:
    """What ``stored_orders`` reads back: the orders and the fight's foes."""
    return {"orders": dict(orders), "foes": list(dict.fromkeys(foes))}


def seeking_line(attempts: list[str]) -> str | None:
    """The party wants a fight and none is on: the storyteller is told to
    stage it or say it is not found (long-adventure-001: "I attack the first
    goblin I see" was narrated as a declaration by the hearth, no goblin)."""
    if not attempts:
        return None
    wanted = "; ".join(attempts)
    return (
        f"The party is looking for a fight ({wanted}). If such foes can plausibly be "
        "met here and now, bring them in this scene and open the fight on its own line "
        "with ENCOUNTER[...]; if none could be here, show plainly that none are found."
    )
