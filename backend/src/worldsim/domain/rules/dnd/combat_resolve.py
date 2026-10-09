"""Deterministic combat tag resolution (owned by DND-WIRE-2).

Deep module: narration text goes in, a full combat report comes out.
No I/O, and the input sheets are never mutated (rolls run against
copies); the caller persists HP deltas and beats. Tags resolve in
source order against one RNG stream, so a seeded stream replays
exactly.

Attackers match by loadout: the first roster sheet carrying the tagged
weapon or spell rolls. Party targets resolve by name; anything else
falls back to the monster tables with ephemeral HP (the monolith never
persisted monster state either). Saves use class saving throws for
adventurers and the precomputed bonuses for monsters.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from worldsim.domain.rules.dnd.combat import (
    roll_attack,
    roll_damage,
    roll_dice,
    roll_save,
)
from worldsim.domain.rules.dnd.core import (
    MonsterRef,
    ability_mod,
    encounter_difficulty,
    find_entry,
    ordinal,
    slugify,
)
from worldsim.domain.rules.dnd.data import (
    DataTables,
    dict_field,
    entry,
    int_field,
    list_field,
    str_field,
    table,
)
from worldsim.domain.rules.dnd.deeds import (
    Deed,
    after_encounter,
    deed_lines,
    group_size,
    helper_lines,
    line_actor,
    opening_lines,
    order_target,
)
from worldsim.domain.rules.dnd.progress import (
    LevelGain,
    free_slot,
    gain_xp,
    long_rest,
    monster_kind,
    pool_number,
    spend_slot,
)
from worldsim.domain.rules.dnd.sheets import (
    Sheet,
    armor_ac,
    sheet_mod,
    sheet_prof,
    spell_attack_bonus,
    spellcasting_ability,
    weapon_attack_bonus,
    weapon_damage,
)
from worldsim.domain.rules.dnd.spells import resolve_spell
from worldsim.domain.rules.dnd.tags import (
    parse_attack_tag,
    parse_cast_tag,
    parse_condition_tag,
    parse_encounter_tag,
)

_TAG_RE = re.compile(
    r"^\s*(ENCOUNTER|ATTACK|CAST|CONDITION)\s*\[([^\]]+)\]",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class CombatBeat:
    text: str
    cited: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TagOutcome:
    """One resolved tag: ``text`` is the audit line; the rest is the roll
    in parts, so a reader can show who rolled what against what."""

    kind: str
    text: str
    attacker_key: str | None = None
    target_key: str | None = None
    actor: str | None = None
    target: str | None = None
    using: str | None = None
    roll: int | None = None
    natural: int | None = None
    ac: int | None = None
    dc: int | None = None
    #: hit, miss, crit, saved, half, failed, healed (None: no roll).
    result: str | None = None
    amount: int | None = None
    damage_type: str | None = None
    hp_before: int | None = None
    hp_after: int | None = None
    #: The target is one of the foes (not the party).
    target_foe: bool = False
    #: The actor is one of the foes.
    actor_foe: bool = False
    #: XP each party member got (kind ``xp``) or the level reached (``level``).
    share: int | None = None
    level: int | None = None
    #: Choices a level left to its player: ``ability``, ``spells`` (comma-joined).
    choose: str | None = None


@dataclass(frozen=True)
class MonsterState:
    """Live pool carried in: one row per world and name key."""

    key: str
    name: str
    hp_current: int
    hp_max: int
    ac: int


@dataclass(frozen=True)
class MonsterResult:
    """Pool to persist: working HP plus the max/AC that own it."""

    key: str
    name: str
    hp_current: int
    hp_max: int
    ac: int
    spawned: bool


@dataclass(frozen=True)
class CombatReport:
    outcomes: list[TagOutcome] = field(default_factory=list)
    hp: dict[str, int] = field(default_factory=dict)
    conditions: dict[str, list[str]] = field(default_factory=dict)
    monsters: dict[str, MonsterResult] = field(default_factory=dict)
    beats: list[CombatBeat] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    #: Monster pool keys this fight touched, in the order they appeared.
    foes: list[str] = field(default_factory=list)
    #: Every party sheet this scene changed (HP, conditions, slots, XP, level),
    #: by name key: what the caller saves.
    sheets: dict[str, Sheet] = field(default_factory=dict)
    #: Foes that fell in this scene, and the levels the party gained.
    defeated: list[str] = field(default_factory=list)
    levels: list[LevelGain] = field(default_factory=list)
    #: Tag lines added from the party's own words (``deeds``), not the storyteller's.
    deeds: int = 0
    #: Blows companions struck beside the party with nothing else making them act.
    helped: int = 0


@dataclass
class _MonsterTarget:
    label: str
    ac: int
    hp: int
    key: str


_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}
_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_LEAD_ORDINAL_RE = re.compile(
    r"^(\d+)(?:st|nd|rd|th)\s+(.+)$|^(" + "|".join(_ORDINAL_WORDS) + r")\s+(.+)$",
    re.IGNORECASE,
)
_TAIL_NUMBER_RE = re.compile(r"^(.+?)\s*(?:#|no\.?\s*|number\s+)?(\d+)$", re.IGNORECASE)


def foe_name_parts(text: str) -> tuple[str, int | None]:
    """``Goblin 2``, ``goblin #2``, ``the second goblin``, ``2nd goblin``:
    the creature and which one of a numbered group (``None``: any)."""
    plain = _ARTICLE_RE.sub("", text.strip())
    lead = _LEAD_ORDINAL_RE.match(plain)
    if lead:
        if lead.group(1):
            return lead.group(2).strip(), int(lead.group(1))
        return lead.group(4).strip(), _ORDINAL_WORDS[lead.group(3).lower()]
    tail = _TAIL_NUMBER_RE.match(plain)
    if tail:
        return tail.group(1).strip(), int(tail.group(2))
    return plain, None


def _numbered(name: str, number: int) -> str:
    return f"{name} {number}"


def _possessive(label: str) -> str:
    """``The goblin's`` for a lone foe, ``Goblin 2's`` for one of a group."""
    return f"{label}'s" if label[-1:].isdigit() else f"The {label.lower()}'s"


#: The ``at Wren`` tail of an attack tag; what is left names the striker.
_ATTACK_SUBJECT_RE = re.compile(r"\b(?:at|on|against|vs\.?)\s+.+$", re.IGNORECASE)


def _first_strike(row: dict[str, Any]) -> tuple[str, int, str, str] | None:
    """A monster's first weapon action: (name, to-hit, damage dice, type)."""
    for raw in list_field(row, "actions"):
        if not isinstance(raw, dict):
            continue
        action = cast("dict[str, Any]", raw)
        bonus = action.get("attack_bonus")
        if not isinstance(bonus, int) or isinstance(bonus, bool):
            continue
        for hit in list_field(action, "damage"):
            if isinstance(hit, dict):
                damage = cast("dict[str, Any]", hit)
                dice = str_field(damage, "dice")
                if dice:
                    name = str_field(action, "name") or "Strike"
                    return name, bonus, dice, str_field(damage, "type") or "damage"
    return None


def _sheet_key(name: str) -> str:
    return f"dnd-sheet:{slugify(name)}"


def _party_position(order: list[Sheet], keys: list[str], target: str | None) -> int | None:
    if not target:
        return None
    want = target.strip().lower()
    for pos, sheet in enumerate(order):
        if sheet.name.lower() == want or keys[pos] == want:
            return pos
    return None


def _monster_target(
    tables: DataTables, monsters: dict[str, Any], name: str | None
) -> _MonsterTarget:
    found = find_entry(monsters, name or "")
    if found is None:
        return _MonsterTarget(label=name or "the air", ac=10, hp=0, key=(name or "unknown").lower())
    row = found.entry
    return _MonsterTarget(
        label=str(row.get("name", name)),
        ac=int_field(row, "ac", 10),
        hp=int_field(row, "hp"),
        key=found.index,
    )


def _save_bonus(
    tables: DataTables, sheet: Sheet, ability: str, monster: dict[str, Any] | None
) -> int:
    if monster is not None:
        saves = dict_field(monster, "saves")
        direct = saves.get(ability)
        if isinstance(direct, int) and not isinstance(direct, bool):
            return direct
        return ability_mod(int_field(dict_field(monster, "stats"), ability, 10))
    mod = sheet_mod(sheet, ability)
    cls = entry(table(tables, "classes"), sheet.character_class)
    throws = [str(t).lower() for t in list_field(cls, "saving_throws")]
    if ability in throws:
        mod += sheet_prof(sheet)
    return mod


def resolve_narration_tags(
    text: str,
    sheets: list[Sheet],
    tables: DataTables,
    rng: Callable[[], float] | None = None,
    live: list[MonsterState] | None = None,
    *,
    day: int | None = None,
    fighting: list[str] | None = None,
    deeds: list[Deed] | None = None,
    chooses: set[str] | None = None,
    strike_back: bool = False,
    present: set[str] | None = None,
    orders: dict[str, str] | None = None,
    recent: str = "",
    slain_lately: set[str] | None = None,
) -> CombatReport:
    """Resolve every combat tag in narration order. Inputs are never mutated.

    ``live`` carries pools from earlier scenes; unknown keys start at the
    table maximum. Each foe of a group has its own pool: ``ENCOUNTER[2x
    goblin]`` makes Goblin 1 and Goblin 2 (keys ``goblin-1``/``goblin-2``);
    a lone foe keeps the plain name. A fresh ENCOUNTER respawns to full,
    unless foes of that kind still stand in the fight that is on
    (``fighting``): then the newcomers are numbered after them. A target
    named without a number is the first of its kind still standing.

    ``day`` is the story day: levelled spells spend a slot of the day
    (slots spent on an earlier day are back). Foes that fall give their
    XP to the party, shared evenly, and a crossed threshold levels up;
    members in ``chooses`` (name keys: the player's hero) make that level's
    choices themselves. A sheet that wakes on a later day has had the
    night's long rest first.

    ``deeds`` are what party members tried this scene in their own words:
    a plain attack or spell the storyteller did not tag rolls anyway.
    ``strike_back``: the party is in this scene. When it fought here and
    the storyteller tagged no foe's blow, each foe still standing strikes
    once (at the one who acted, else the first party member standing). And
    once no fight is on (or this scene ends it), whoever was down gets back
    up with 1 hit point: there is no death and dying.
    ``present`` are the party members in this scene: companions among them
    (not in ``chooses``) whom nothing had act fight beside the party: at the
    foe the hero's ``orders`` (their words to a companion, by key) name,
    else the most wounded foe standing.
    """
    if not sheets or not (text or deeds):
        return CombatReport()
    order = [long_rest(sheet, day) for sheet in sheets]
    woke = {
        slugify(sheet.name) for sheet, was in zip(order, sheets, strict=True) if sheet is not was
    }
    currents = {id(sheet): (sheet.hp.current if sheet.hp else 0) for sheet in order}
    maxima = {id(sheet): (sheet.hp.max if sheet.hp else 0) for sheet in order}
    keys = [slugify(sheet.name) for sheet in order]
    key_of = {id(sheet): key for sheet, key in zip(order, keys, strict=True)}
    monsters = table(tables, "monsters")
    weapons = table(tables, "weapons")
    carried = {state.key: state for state in live or []}
    monster_hp = {
        key: max(0, min(state.hp_current, state.hp_max)) for key, state in carried.items()
    }
    monster_meta: dict[str, _MonsterTarget] = {}
    for key, state in carried.items():
        monster_meta[key] = _MonsterTarget(label=state.name, ac=state.ac, hp=state.hp_max, key=key)
    outcomes: list[TagOutcome] = []
    beats: list[CombatBeat] = []
    unresolved: list[str] = []
    hp_updates: dict[str, int] = {}
    new_conditions: dict[str, list[str]] = {}
    # Slots are spent on working copies; the inputs stay untouched.
    casting = {id(sheet): sheet.model_copy(deep=True) for sheet in order}
    cast_keys: set[str] = set()
    defeated: list[str] = []
    on_now = [key for key in fighting or [] if key in monster_meta]
    # The party's own words: a plain attack or spell rolls even untagged.
    standing_kinds: list[tuple[str, str]] = []
    for key in on_now:
        kind = monster_kind(key, monsters)
        if monster_hp.get(key, 0) > 0 and kind in monsters:
            standing_kinds.append((kind, str(entry(monsters, kind).get("name", kind))))
    for match in _TAG_RE.finditer(text):
        if match.group(1).upper() == "ENCOUNTER":
            for ref in parse_encounter_tag(match.group(2), tables):
                standing_kinds.append((ref.index, ref.name))
    # Kinds slain lately (the last fight, while it lingers): the player's
    # words alone do not bring one straight back. Not forever: after a goblin
    # fell on the first evening, no goblin could ever be met again by the
    # player's words (long-adventure-001). None: every kind ever slain.
    fallen_kinds = (
        set(slain_lately)
        if slain_lately is not None
        else {monster_kind(key, monsters) for key, hp in monster_hp.items() if hp <= 0}
    )
    if not on_now:
        # A fight begun without an ENCOUNTER: open it, as large as the words
        # count ("two goblins"), so the second goblin is a real foe.
        opened = opening_lines(text, deeds or [], order, tables, fallen_kinds, recent)
        if opened:
            text = "\n".join([*opened, text])
            for line in opened:
                inner = line[line.index("[") + 1 : line.index("]")]
                for ref in parse_encounter_tag(inner, tables):
                    standing_kinds.append((ref.index, ref.name))

    def most_wounded(met: list[str] | None = None) -> str | None:
        """The foe standing (in the fight that is on, or met in this scene)
        with the least health left, by share."""
        up = [
            k
            for k in list(dict.fromkeys(on_now + list(met or [])))
            if k in monster_meta and monster_hp.get(k, 0) > 0
        ]
        if not up:
            return None
        key = min(up, key=lambda k: monster_hp[k] / max(1, monster_meta[k].hp))
        return monster_meta[key].label

    helped = 0
    if strike_back:
        extra = helper_lines(
            text,
            order,
            keys,
            (present or set()) - (chooses or set()),
            {deed.key for deed in deeds or []},
            list(dict.fromkeys(standing_kinds)),
            tables,
            aim=most_wounded(),
            orders=orders,
        )
        text, helped = after_encounter(text, extra), len(extra)
    text, deed_count = deed_lines(
        text,
        deeds or [],
        order,
        keys,
        tables,
        list(dict.fromkeys(standing_kinds)),
        fallen_kinds,
    )

    def cite(*members: str | None) -> list[str]:
        return [_sheet_key(key) for key in members if key]

    def hurt_party(pos: int, amount: int) -> tuple[int, int]:
        sheet = order[pos]
        before = currents[id(sheet)]
        after = max(0, before - amount)
        currents[id(sheet)] = after
        hp_updates[key_of[id(sheet)]] = after
        return before, after

    def mend_party(pos: int, amount: int) -> tuple[int, int]:
        sheet = order[pos]
        before = currents[id(sheet)]
        after = min(maxima[id(sheet)], before + amount)
        currents[id(sheet)] = after
        hp_updates[key_of[id(sheet)]] = after
        return before, after

    damaged: set[str] = set()
    spawned: set[str] = set()

    def hurt_monster(target: _MonsterTarget, amount: int) -> tuple[int, int]:
        monster_meta.setdefault(target.key, target)
        start = monster_hp.get(target.key, target.hp)
        after = max(0, start - amount)
        monster_hp[target.key] = after
        if after != start:
            damaged.add(target.key)
        if start > 0 and after == 0 and target.key not in defeated:
            defeated.append(target.key)
        return start, after

    foes: list[str] = []
    # Pools first met mid-fight (no ENCOUNTER, nothing carried): kept, so
    # the next scene and the party panel know them.
    implied: set[str] = set()

    def saw(key: str) -> None:
        if key not in foes:
            foes.append(key)

    def meet(target: _MonsterTarget) -> None:
        """A real monster (one the tables know) joins this fight's foes."""
        if monster_kind(target.key, monsters) not in monsters and target.key not in monster_meta:
            return
        if target.key not in monster_hp:
            monster_meta.setdefault(target.key, target)
            monster_hp[target.key] = target.hp
            implied.add(target.key)
        saw(target.key)

    def of_kind(kind: str) -> list[str]:
        """Known pools of one kind: this scene's foes, the fight that is on,
        then every pool carried in, by number."""
        carried_keys = sorted(monster_meta, key=lambda k: (pool_number(k), k))
        seen: list[str] = []
        for key in [*foes, *on_now, *carried_keys]:
            if key not in seen and key in monster_meta and monster_kind(key, monsters) == kind:
                seen.append(key)
        return seen

    def pick_foe(text: str | None) -> _MonsterTarget | None:
        """The foe a tag aims at: a numbered one, else the first standing."""
        if not text:
            return None
        base, number = foe_name_parts(text)
        found = find_entry(monsters, base)
        if found is None:
            return None
        kind = found.index
        if number is not None:
            for key in (f"{kind}-{number}", kind) if number == 1 else (f"{kind}-{number}",):
                if key in monster_meta:
                    return monster_meta[key]
        known = of_kind(kind)
        if known:
            standing = [k for k in known if monster_hp.get(k, monster_meta[k].hp) > 0]
            if standing:
                return monster_meta[standing[0]]
            return monster_meta[kind] if kind in monster_meta else monster_meta[known[0]]
        return _MonsterTarget(
            label=str(found.entry.get("name", base)),
            ac=int_field(found.entry, "ac", 10),
            hp=int_field(found.entry, "hp"),
            key=kind,
        )

    def aim(text: str | None) -> _MonsterTarget:
        return pick_foe(text) or _monster_target(tables, monsters, text)

    def slain(text: str | None) -> bool:
        """The foe a tag aims at has already fallen: a blow there rolls nothing."""
        foe = pick_foe(text)
        return foe is not None and foe.key in monster_hp and monster_hp[foe.key] <= 0

    # The foe each companion was told to take ("Ash, take the third goblin").
    ordered = {
        key: phrase
        for key, words in (orders or {}).items()
        if (phrase := order_target(words, list(dict.fromkeys(standing_kinds))))
    }

    def retarget(akey: str, target: str | None) -> str | None:
        """Where a party member's blow lands: at a party member as tagged;
        else the foe they were told to take while it stands; else, when the
        tagged foe has already fallen, the most wounded foe standing (None:
        nobody is left). A blow at the second goblin, slain a moment before
        by a companion, rolled nothing with Goblin 3 still standing."""
        if _party_position(order, keys, target) is not None:
            return target
        told = ordered.get(akey)
        if told and pick_foe(told) is not None and not slain(told):
            return told
        if target and slain(target):
            return most_wounded(foes)
        return target

    def foe_strike(inner: str, target_name: str | None) -> bool:
        """``ATTACK[goblin at Wren]``: a standing foe swings its first weapon
        at a party member. False when no such foe, target or weapon."""
        pos = _party_position(order, keys, target_name)
        subject = _ATTACK_SUBJECT_RE.sub("", inner).strip()
        foe = pick_foe(subject)
        if pos is None or foe is None:
            return False
        action = _first_strike(entry(monsters, monster_kind(foe.key, monsters)))
        if action is None:
            return False
        if monster_hp.get(foe.key, foe.hp) <= 0:
            return False  # the fallen do not strike
        meet(foe)
        using, bonus, dice, dtype = action
        sheet = order[pos]
        target_ac = armor_ac(tables, sheet)
        attack = roll_attack(bonus, target_ac, rng)
        parts: dict[str, Any] = {
            "actor": foe.label,
            "target": sheet.name,
            "using": using,
            "roll": attack.total,
            "natural": attack.nat,
            "ac": target_ac,
            "actor_foe": True,
        }
        tkey = keys[pos]
        if not attack.hit:
            outcomes.append(
                TagOutcome(
                    kind="attack",
                    target_key=tkey,
                    text=f"{foe.label} misses {sheet.name} ({attack.total} vs AC {target_ac}).",
                    result="miss",
                    **parts,
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{_possessive(foe.label)} {using.lower()} misses {sheet.name}.",
                    cited=cite(tkey),
                )
            )
            return True
        rolled = roll_damage(dice, rng, attack.crit)
        before, after = hurt_party(pos, rolled)
        crit = " Critical!" if attack.crit else ""
        outcomes.append(
            TagOutcome(
                kind="attack",
                target_key=tkey,
                text=f"{foe.label} hits {sheet.name} for {rolled} {dtype}.{crit} "
                f"({before}->{after} HP)",
                result="crit" if attack.crit else "hit",
                amount=rolled,
                damage_type=dtype,
                hp_before=before,
                hp_after=after,
                **parts,
            )
        )
        beats.append(
            CombatBeat(
                text=f"{_possessive(foe.label)} {using.lower()} hits {sheet.name} "
                f"for {rolled} {dtype}.{crit}",
                cited=cite(tkey),
            )
        )
        return True

    def carrier(key: str, *, spell: bool, named: Sheet | None = None) -> Sheet | None:
        """Who a loadout tag means: the party member its line names, when they
        carry it; else the first carrier still standing, else the first."""
        having = [s for s in order if key in (s.spells if spell else s.weapons)]
        if named is not None and named in having:
            return named
        return next((s for s in having if currents[id(s)] > 0), having[0] if having else None)

    def come_to() -> None:
        """Everyone down gets back up with 1 hit point (the fight is over)."""
        for pos, sheet in enumerate(order):
            if sheet.hp is not None and currents[id(sheet)] <= 0:
                before, after = mend_party(pos, 1)
                outcomes.append(
                    TagOutcome(
                        kind="recover",
                        attacker_key=keys[pos],
                        text=f"{sheet.name} gets back up ({before}->{after} HP).",
                        actor=sheet.name,
                        hp_before=before,
                        hp_after=after,
                    )
                )
                beats.append(
                    CombatBeat(text=f"{sheet.name} gets back up, battered.", cited=cite(keys[pos]))
                )

    if strike_back and not on_now:
        come_to()

    for match in _TAG_RE.finditer(text):
        kind, inner = match.group(1).upper(), match.group(2).strip()
        line_end = text.find("\n", match.end())
        voiced = line_actor(text[match.end() : line_end if line_end >= 0 else len(text)], order)
        if kind == "ENCOUNTER":
            refs = parse_encounter_tag(inner, tables)
            if not refs:
                unresolved.append(match.group(0))
                continue
            # The tag counts fewer than the prose tells ("Two goblins burst in"
            # under ENCOUNTER[goblin]): the prose is what the reader saw.
            refs = [
                ref.model_copy(update={"count": max(ref.count, group_size([text], ref.name))})
                for ref in refs
            ]
            diff = encounter_difficulty(
                [s.level for s in order],
                [MonsterRef(index=r.index, count=r.count) for r in refs],
                tables,
            )
            named: list[str] = []
            for ref in refs:
                encounter_row = entry(monsters, ref.index)
                label = str(encounter_row.get("name", ref.name))
                # Foes of this kind still standing in the fight that is on:
                # the newcomers join them, numbered after them.
                standing = [
                    key
                    for key in of_kind(ref.index)
                    if (key in foes or key in on_now) and monster_hp.get(key, 0) > 0
                ]
                if standing:
                    start = max(pool_number(key) for key in of_kind(ref.index)) + 1
                    numbers = list(range(start, start + ref.count))
                elif ref.count > 1:
                    numbers = list(range(1, ref.count + 1))
                else:
                    numbers = [0]
                for number in numbers:
                    key = f"{ref.index}-{number}" if number else ref.index
                    fresh = _MonsterTarget(
                        label=_numbered(label, number) if number else label,
                        ac=int_field(encounter_row, "ac", 10),
                        hp=int_field(encounter_row, "hp"),
                        key=key,
                    )
                    monster_hp[key] = fresh.hp
                    monster_meta[key] = fresh
                    spawned.add(key)
                    saw(key)
                    named.append(fresh.label)
            described = ", ".join(f"{r.count}x {r.name}" if r.count > 1 else r.name for r in refs)
            outcomes.append(
                TagOutcome(
                    kind="encounter",
                    text=f"Encounter: {described} ({diff.difficulty}, "
                    f"{diff.adjusted_xp} adjusted XP).",
                    target=", ".join(named),
                    result=diff.difficulty,
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{', '.join(named)} bar the way ({diff.difficulty} encounter).",
                    cited=[_sheet_key(key) for key in keys],
                )
            )
            continue
        if kind == "ATTACK":
            tag = parse_attack_tag(inner, tables)
            attacker = None
            if tag is not None:
                attacker = carrier(tag.index, spell=False, named=voiced) if tag.index else None
                if attacker is None and tag.index is None:
                    attacker = carrier(tag.name, spell=False, named=voiced)
            if tag is not None and attacker is None:
                # ``ATTACK[goblin at Wren]``: a foe strikes back with its own weapon.
                if not foe_strike(inner, tag.target):
                    unresolved.append(match.group(0))
                continue
            if tag is None or attacker is None or currents[id(attacker)] <= 0:
                # A hero who is down does not swing.
                unresolved.append(match.group(0))
                continue
            akey = key_of[id(attacker)]
            aimed = retarget(akey, tag.target)
            if aimed is None and tag.target:
                unresolved.append(match.group(0))
                continue
            if (
                aimed
                and _party_position(order, keys, aimed) is None
                and pick_foe(aimed) is None
                and find_entry(monsters, foe_name_parts(aimed)[0]) is None
            ):
                # Not a creature the tables know ("ATTACK[longsword at enemy]"):
                # no roll; it read "hits enemy for 9 slashing (0->0 HP)".
                unresolved.append(match.group(0))
                continue
            tag = tag.model_copy(update={"target": aimed})
            weapon = entry(weapons, tag.index) if tag.index else {}
            bonus = weapon_attack_bonus(tables, attacker, weapon)
            pos = _party_position(order, keys, tag.target)
            if pos is not None:
                target_ac = armor_ac(tables, order[pos])
                target: str | _MonsterTarget = order[pos].name
                tkey: str | None = keys[pos]
            else:
                if slain(tag.target):
                    unresolved.append(match.group(0))
                    continue
                target = aim(tag.target)
                target_ac = target.ac
                tkey = None
                meet(target)
            label = target if isinstance(target, str) else target.label
            attack = roll_attack(bonus, target_ac, rng)
            parts: dict[str, Any] = {
                "actor": attacker.name,
                "target": label,
                "using": tag.name,
                "roll": attack.total,
                "natural": attack.nat,
                "ac": target_ac,
                "target_foe": pos is None,
            }
            if not attack.hit:
                outcomes.append(
                    TagOutcome(
                        kind="attack",
                        attacker_key=akey,
                        text=f"{attacker.name} misses {label} ({attack.total} vs AC {target_ac}).",
                        result="miss",
                        **parts,
                    )
                )
                beats.append(
                    CombatBeat(
                        text=f"{attacker.name}'s {tag.name} misses {label}.",
                        cited=cite(akey, tkey),
                    )
                )
                continue
            damage = dict_field(weapon, "damage")
            dice = str_field(damage, "dice")
            dtype = str_field(damage, "type") or "damage"
            # The weapon's ability adds to its damage as to its aim (5e).
            rolled = weapon_damage(tables, attacker, weapon, roll_damage(dice, rng, attack.crit))
            if pos is not None:
                before, after = hurt_party(pos, rolled)
            else:
                assert isinstance(target, _MonsterTarget)
                before, after = hurt_monster(target, rolled)
            crit = " Critical!" if attack.crit else ""
            outcomes.append(
                TagOutcome(
                    kind="attack",
                    attacker_key=akey,
                    target_key=tkey,
                    text=f"{attacker.name} hits {label} for {rolled} {dtype}.{crit} "
                    f"({before}->{after} HP)",
                    result="crit" if attack.crit else "hit",
                    amount=rolled,
                    damage_type=dtype,
                    hp_before=before,
                    hp_after=after,
                    **parts,
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{attacker.name}'s {tag.name} hits {label} for {rolled} {dtype}.{crit}",
                    cited=cite(akey, tkey),
                )
            )
            continue
        if kind == "CAST":
            tag = parse_cast_tag(inner, tables)
            attacker = None
            if tag is not None and tag.index:
                attacker = carrier(tag.index, spell=True, named=voiced)
            if tag is not None and attacker is not None and tag.target:
                aimed = retarget(key_of[id(attacker)], tag.target)
                tag = tag.model_copy(update={"target": aimed or tag.target})
            if (
                tag is None
                or attacker is None
                or currents[id(attacker)] <= 0
                or (_party_position(order, keys, tag.target) is None and slain(tag.target))
            ):
                unresolved.append(match.group(0))
                continue
            akey = key_of[id(attacker)]
            spell_row = entry(table(tables, "spells"), tag.index or "")
            spell_level = int_field(spell_row, "level")
            slot = tag.slot_level
            if spell_row and spell_level > 0:
                want = max(spell_level, tag.slot_level or spell_level)
                book = casting[id(attacker)]
                slot = free_slot(tables, book, want, day)
                if slot is None:
                    spell_name = str(spell_row.get("name", tag.name))
                    outcomes.append(
                        TagOutcome(
                            kind="cast",
                            attacker_key=akey,
                            text=f"{attacker.name} has no {ordinal(want)}-level spell slot "
                            f"left: {spell_name} fails.",
                            actor=attacker.name,
                            target=tag.target,
                            using=spell_name,
                            result="no-slot",
                            level=want,
                        )
                    )
                    beats.append(
                        CombatBeat(
                            text=f"{attacker.name} reaches for {spell_name}, "
                            "but has no spell slot left.",
                            cited=cite(akey),
                        )
                    )
                    continue
                spend_slot(book, slot, day)
                cast_keys.add(akey)
            resolved = resolve_spell(tag.index or "", attacker, tables, slot)
            if resolved is None:
                unresolved.append(match.group(0))
                continue
            pos = _party_position(order, keys, tag.target)
            if resolved.damage is None and resolved.heal_dice is None:
                outcomes.append(
                    TagOutcome(
                        kind="cast",
                        attacker_key=akey,
                        text=f"{attacker.name} casts {resolved.name} "
                        f"({tag.target or 'no target'}).",
                        actor=attacker.name,
                        target=tag.target,
                        using=resolved.name,
                    )
                )
                beats.append(
                    CombatBeat(text=f"{attacker.name} casts {resolved.name}.", cited=cite(akey))
                )
                continue
            if resolved.damage is None:
                assert resolved.heal_dice is not None
                ability = spellcasting_ability(tables, attacker) or "wis"
                dice = resolved.heal_dice.replace("MOD", str(sheet_mod(attacker, ability)))
                rolled = roll_dice(dice, rng)
                mended: tuple[int, int] | None = None
                if pos is not None:
                    mended = mend_party(pos, rolled)
                    label, tkey = order[pos].name, keys[pos]
                    trail = f" ({mended[0]}->{mended[1]} HP)"
                else:
                    label, tkey, trail = tag.target or "the air", None, " (no one to mend)"
                outcomes.append(
                    TagOutcome(
                        kind="cast",
                        attacker_key=akey,
                        target_key=tkey,
                        text=f"{attacker.name} heals {label} for {rolled}.{trail}",
                        actor=attacker.name,
                        target=label,
                        using=resolved.name,
                        result="healed",
                        amount=rolled,
                        hp_before=mended[0] if mended else None,
                        hp_after=mended[1] if mended else None,
                    )
                )
                beats.append(
                    CombatBeat(
                        text=f"{attacker.name}'s {resolved.name} mends {label} for {rolled}.",
                        cited=cite(akey, tkey),
                    )
                )
                continue
            assert resolved.damage is not None
            dtype = resolved.damage.kind or "damage"
            struck: _MonsterTarget | None = None
            spell: dict[str, Any] = {
                "actor": attacker.name,
                "using": resolved.name,
                "target_foe": pos is None,
                "damage_type": dtype,
            }
            if resolved.attack_type is not None:
                bonus = spell_attack_bonus(tables, attacker) or 0
                if pos is not None:
                    target_ac = armor_ac(tables, order[pos])
                    label, tkey = order[pos].name, keys[pos]
                else:
                    monster = aim(tag.target)
                    struck = monster
                    target_ac, label, tkey = monster.ac, monster.label, None
                    meet(monster)
                attack = roll_attack(bonus, target_ac, rng)
                spell.update(target=label, roll=attack.total, natural=attack.nat, ac=target_ac)
                if not attack.hit:
                    outcomes.append(
                        TagOutcome(
                            kind="cast",
                            attacker_key=akey,
                            text=f"{resolved.name} misses {label} "
                            f"({attack.total} vs AC {target_ac}).",
                            result="miss",
                            **spell,
                        )
                    )
                    beats.append(
                        CombatBeat(
                            text=f"{attacker.name}'s {resolved.name} misses {label}.",
                            cited=cite(akey, tkey),
                        )
                    )
                    continue
                rolled = roll_damage(resolved.damage.dice, rng, attack.crit)
                crit = " Critical!" if attack.crit else ""
                detail = f"hits {label} for {rolled} {dtype}.{crit}"
                spell["result"] = "crit" if attack.crit else "hit"
            else:
                dc = resolved.dc
                save_ability = (dc.kind if dc else None) or "dex"
                dc_value = dc.dc_value if dc and dc.dc_value is not None else 10
                success_word = (dc.success if dc and dc.success else None) or "none"
                if pos is not None:
                    bonus = _save_bonus(tables, order[pos], save_ability, None)
                    label, tkey = order[pos].name, keys[pos]
                else:
                    monster = aim(tag.target)
                    struck = monster
                    kind_key = monster_kind(monster.key, monsters)
                    row = entry(monsters, kind_key) if kind_key in monsters else {}
                    bonus = _save_bonus(tables, attacker, save_ability, row or None)
                    label, tkey = monster.label, None
                    meet(monster)
                save = roll_save(bonus, dc_value, rng)
                if save.success and success_word == "half":
                    rolled = math.floor(roll_dice(resolved.damage.dice, rng) / 2)
                    how = f"saves ({save.total} vs DC {dc_value}), half damage"
                    verdict = "half"
                elif save.success:
                    rolled, how = 0, f"saves ({save.total} vs DC {dc_value}), unharmed"
                    verdict = "saved"
                else:
                    rolled = roll_dice(resolved.damage.dice, rng)
                    how = f"fails ({save.total} vs DC {dc_value})"
                    verdict = "failed"
                detail = f"{label} {how} for {rolled} {dtype}."
                spell.update(
                    target=label, roll=save.total, natural=save.nat, dc=dc_value, result=verdict
                )
            if pos is not None:
                before, after = hurt_party(pos, rolled)
                trail = f" ({before}->{after} HP)"
            else:
                assert struck is not None
                before, after = hurt_monster(struck, rolled)
                trail = f" ({before}->{after} HP)"
            outcomes.append(
                TagOutcome(
                    kind="cast",
                    attacker_key=akey,
                    target_key=tkey,
                    text=f"{resolved.name} {detail}{trail}",
                    amount=rolled,
                    hp_before=before,
                    hp_after=after,
                    **spell,
                )
            )
            beats.append(
                CombatBeat(
                    text=f"{attacker.name}'s {resolved.name} {detail}",
                    cited=cite(akey, tkey),
                )
            )
            continue
        if kind == "CONDITION":
            tag = parse_condition_tag(inner, tables)
            if tag is None:
                unresolved.append(match.group(0))
                continue
            pos = _party_position(order, keys, tag.target)
            if tag.index:
                label = str(entry(table(tables, "conditions"), tag.index).get("name", tag.name))
            else:
                label = tag.name
            if pos is not None:
                seen = new_conditions.get(keys[pos], list(order[pos].conditions))
                if label not in seen:
                    seen = seen + [label]
                new_conditions[keys[pos]] = seen
                tkey, tlabel = keys[pos], order[pos].name
            else:
                tkey, tlabel = None, tag.target or "the air"
            span = f" ({tag.duration})" if tag.duration else ""
            outcomes.append(
                TagOutcome(
                    kind="condition",
                    target_key=tkey,
                    text=f"{label} on {tlabel}{span}.",
                    target=tlabel,
                    using=label,
                    target_foe=pos is None,
                )
            )
            beats.append(CombatBeat(text=f"{tlabel} is {label.lower()}{span}.", cited=cite(tkey)))
            continue
        unresolved.append(match.group(0))

    # Foes the storyteller left silent strike back: a fight goes both ways.
    fought = any(o.target_foe and not o.actor_foe for o in outcomes) or any(
        o.kind == "encounter" for o in outcomes
    )
    if strike_back and fought and not any(o.actor_foe for o in outcomes):
        acted = [k for d in deeds or [] for k in [d.key] if k in keys]
        aim_at = next(
            (
                order[keys.index(k)].name
                for k in [*acted, *keys]
                if currents[id(order[keys.index(k)])] > 0
            ),
            None,
        )
        standing_foes = [
            key
            for key in dict.fromkeys([*foes, *on_now])
            if key in monster_meta and monster_hp.get(key, 0) > 0
        ]
        for key in standing_foes[:3]:
            if aim_at is None:
                break
            label = monster_meta[key].label
            foe_strike(f"{label} at {aim_at}", aim_at)
            if currents[id(order[keys.index(slugify(aim_at))])] <= 0:
                aim_at = next((s.name for s in order if currents[id(s)] > 0), None)

    # The fight ended here (its foes all down): the fallen get back up.
    in_fight = list(dict.fromkeys([*foes, *on_now]))
    if (
        strike_back
        and in_fight
        and all(monster_hp.get(key, 0) <= 0 for key in in_fight if key in monster_meta)
    ):
        come_to()

    # Foes that fell give their XP to the whole party, shared evenly.
    working = {key_of[id(sheet)]: casting[id(sheet)] for sheet in order}
    for sheet in order:
        book = working[key_of[id(sheet)]]
        if book.hp is not None:
            book.hp = book.hp.model_copy(update={"current": currents[id(sheet)]})
        key = key_of[id(sheet)]
        if key in new_conditions:
            book.conditions = list(new_conditions[key])
    changed: set[str] = set(hp_updates) | set(new_conditions) | cast_keys | woke
    gains: list[LevelGain] = []
    total_xp = sum(
        int_field(entry(monsters, monster_kind(key, monsters)), "xp") for key in defeated
    )
    if total_xp > 0:
        share = total_xp // len(order)
        fallen = ", ".join(monster_meta[key].label for key in defeated)
        outcomes.append(
            TagOutcome(
                kind="xp",
                text=f"Defeated {fallen}: {total_xp} XP, {share} each.",
                target=fallen,
                amount=total_xp,
                share=share,
            )
        )
        beats.append(
            CombatBeat(
                text=f"The party earns {total_xp} XP for defeating {fallen}.",
                cited=[_sheet_key(key) for key in keys],
            )
        )
        if share > 0:
            for key in keys:
                for gained in gain_xp(
                    tables, working[key], share, chooses=key in (chooses or set())
                ):
                    gains.append(gained)
                    trail = f", proficiency +{gained.prof_bonus}" if gained.prof_changed else ""
                    if gained.improved:
                        trail += ", " + ", ".join(
                            f"{ability.upper()} +{step}"
                            for ability, step in gained.improved.items()
                        )
                    outcomes.append(
                        TagOutcome(
                            kind="level",
                            attacker_key=key,
                            text=f"{gained.name} reaches level {gained.level}: "
                            f"+{gained.hp_gain} hit points{trail}.",
                            actor=gained.name,
                            amount=gained.hp_gain,
                            level=gained.level,
                            choose=",".join(gained.choices) or None,
                        )
                    )
                    beats.append(
                        CombatBeat(
                            text=f"{gained.name} reaches level {gained.level}.",
                            cited=cite(key),
                        )
                    )
                changed.add(key)

    persisted = {
        key: MonsterResult(
            key=key,
            name=monster_meta[key].label,
            hp_current=monster_hp[key],
            hp_max=monster_meta[key].hp,
            ac=monster_meta[key].ac,
            spawned=key in spawned,
        )
        for key in sorted(set(spawned) | damaged | implied)
        if key in monster_meta and key in monster_hp
    }
    return CombatReport(
        outcomes=outcomes,
        hp=hp_updates,
        conditions=new_conditions,
        monsters=persisted,
        beats=beats,
        unresolved=unresolved,
        foes=foes,
        sheets={key: working[key] for key in keys if key in changed},
        defeated=defeated,
        levels=gains,
        deeds=deed_count,
        helped=helped,
    )


#: Fields of a roll the story log shows (the party keys stay internal).
_ROLL_FIELDS = (
    "kind",
    "text",
    "actor",
    "target",
    "using",
    "roll",
    "natural",
    "ac",
    "dc",
    "result",
    "amount",
    "damage_type",
    "hp_before",
    "hp_after",
    "target_foe",
    "actor_foe",
    "share",
    "level",
    "choose",
)


def combat_rolls(outcomes: list[TagOutcome], joined: list[str]) -> list[dict[str, Any]]:
    """The rolls in parts, for the story log; recruits close the list."""
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        row = {name: getattr(outcome, name) for name in _ROLL_FIELDS}
        rows.append({k: v for k, v in row.items() if v is not None and v is not False})
    rows.extend(
        {"kind": "recruit", "text": f"{name} joins the party.", "actor": name} for name in joined
    )
    return rows


def combat_rolls_json(outcomes: list[TagOutcome], joined: list[str]) -> str:
    return json.dumps(combat_rolls(outcomes, joined), separators=(",", ":"))
