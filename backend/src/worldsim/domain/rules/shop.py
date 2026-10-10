"""Goods for sale, and buying them with gold coins (shops-001).

In a combat story some places sell things: a place whose name reads as a
market sells gear, an inn sells meals, ale and rooms, a smithy weapons.
The goods are content (``content/definitions/shop.json``), priced in
whole gold coins for this story's purses. A successful attempt that buys a
good sold where the buyer stands ("I buy a healing potion", "Pay Bram 3
gold coins for a room") takes the price from the purse (more, when the
words pay more), pays the seller when one is aimed at and, for things one
keeps, puts the good in the buyer's hands. A potion of healing heals when
drunk.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldsim.domain.rules.dnd.sheets import Sheet

#: What a place sells by what its name reads as, first match wins.
SELLER_KINDS: tuple[tuple[str, str], ...] = (
    ("smith", r"smith|forge|smithy|armou?ry|anvil"),
    ("inn", r"\binn\b|tavern|hearth|alehouse|taproom|lodge|common room"),
    ("market", r"market|bazaar|square|stalls?|shop|trading post|fair\b|emporium|peddler"),
)


@dataclass(frozen=True)
class Good:
    """One thing for sale."""

    key: str
    name: str
    price: int
    sellers: tuple[str, ...]
    keep: bool
    words: tuple[str, ...]
    description: str
    heals: str | None = None
    #: A night's sleep: the buyer wakes rested (a room at the inn).
    rests: bool = False

    @property
    def priced(self) -> str:
        coins = "gold coin" if self.price == 1 else "gold coins"
        return f"{self.name} ({self.price} {coins})"


def load_goods(path: str | Path) -> dict[str, Good]:
    """The goods file; duplicate keys fail."""
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    goods: dict[str, Good] = {}
    for row in raw["goods"]:
        good = Good(
            key=str(row["key"]),
            name=str(row["name"]),
            price=int(row["price"]),
            sellers=tuple(str(s) for s in row["sellers"]),
            keep=bool(row.get("keep", True)),
            words=tuple(str(w).lower() for w in row["words"]),
            description=str(row.get("description", "")),
            heals=row.get("heals"),
            rests=bool(row.get("rests", False)),
        )
        if good.key in goods:
            raise ValueError(f"duplicate good: {good.key}")
        if good.price < 1:
            raise ValueError(f"a good costs at least one coin: {good.key}")
        goods[good.key] = good
    return goods


def seller_kind(place_name: str) -> str | None:
    """What kind of seller a place is, by its name (None: it sells nothing)."""
    for kind, pattern in SELLER_KINDS:
        if re.search(pattern, place_name, re.IGNORECASE):
            return kind
    return None


def for_sale(place_name: str, goods: dict[str, Good]) -> list[Good]:
    """What is sold at a place, cheapest first."""
    kind = seller_kind(place_name)
    if kind is None:
        return []
    return sorted((g for g in goods.values() if kind in g.sellers), key=lambda g: (g.price, g.name))


def sale_line(place_name: str, goods: list[Good]) -> str | None:
    """The surroundings line: what is for sale here and at what price."""
    if not goods:
        return None
    return (
        f"For sale at {place_name} (paid in gold coins): "
        + ", ".join(g.priced for g in goods)
        + "."
    )


_BUY = re.compile(
    r"\b(?:buy|buys|buying|bought|purchase|purchases|order|orders|rent|rents|hire|"
    r"pay(?:s|ing)?\b[^.;!?]*?\bfor|get me|i'?ll take|trade for)\b",
    re.IGNORECASE,
)
_NOT_BUYING = re.compile(
    r"\b(?:don'?t|do not|won'?t|will not|refuse|pretend|if you|would you|can't afford|"
    r"how much|what does|price of|sell(?:s|ing)?\b)",
    re.IGNORECASE,
)


def good_named(words: str, goods: list[Good]) -> Good | None:
    """The good the words buy, among those sold here (longest name first)."""
    if not _BUY.search(words) or _NOT_BUYING.search(words):
        return None
    lowered = words.lower()
    named = [
        (len(word), good)
        for good in goods
        for word in good.words
        if re.search(rf"\b{re.escape(word)}\b", lowered)
    ]
    return max(named, key=lambda pair: pair[0])[1] if named else None


_DRINK = re.compile(
    r"\b(?:drink|quaff|swallow|down|gulp|uncork|use)(?:s|ing|ed)?\b"
    r"[^.;!?]*\b(?:potion|draught|vial|flask)\b",
    re.IGNORECASE,
)


def drinks_potion(words: str) -> bool:
    """The words drink a healing potion ("I drink the potion of healing")."""
    return bool(_DRINK.search(words)) and not _NOT_BUYING.search(words)


def roll_heal(dice: str, rng: Any) -> int:
    """Roll "2d4+2" style healing with a ``random.Random``-like ``rng``."""
    found = re.fullmatch(r"\s*(\d+)d(\d+)\s*(?:\+\s*(\d+))?\s*", dice)
    if found is None:
        raise ValueError(f"not a dice expression: {dice}")
    count, sides, bonus = int(found.group(1)), int(found.group(2)), int(found.group(3) or 0)
    return sum(int(rng.random() * sides) + 1 for _ in range(count)) + bonus


#: Spoils a kind of seller buys besides its own goods, in gold coins: a
#: fallen foe's weapon at a smithy (less at the market), a pelt at the market.
SPOILS_BOUGHT: dict[str, dict[str, int]] = {
    "smith": {"weapon": 3},
    "market": {"weapon": 2, "pelt": 2},
}

#: The shield goes on the arm only of a calling trained with shields (5e).
SHIELD_CALLINGS = frozenset({"barbarian", "cleric", "druid", "fighter", "paladin", "ranger"})


def sell_price(
    item_key: str, kind: str | None, goods: dict[str, Good], weapon_keys: Collection[str]
) -> int:
    """What a seller of ``kind`` pays for an item: half the price of a good it
    sells itself (rounded down, so a one-coin good is worth nothing back),
    a set price for spoils it takes, else nothing (0)."""
    if kind is None:
        return 0
    good = goods.get(item_key)
    if good is not None:
        return good.price // 2 if kind in good.sellers else 0
    bought = SPOILS_BOUGHT.get(kind, {})
    if item_key in weapon_keys:
        return bought.get("weapon", 0)
    if item_key.endswith("-pelt"):
        return bought.get("pelt", 0)
    return 0


def buyback_line(place_name: str, kind: str | None) -> str | None:
    """The surroundings line: what the place buys back, and for what."""
    if kind is None:
        return None
    spoils = SPOILS_BOUGHT.get(kind, {})
    parts = ["its own goods at half price"]
    if "weapon" in spoils:
        parts.append(f"a fallen foe's weapon for {spoils['weapon']} gold coins")
    if "pelt" in spoils:
        parts.append(f"a pelt for {spoils['pelt']} gold coins")
    return f"{place_name} buys back " + ", ".join(parts) + "."


_SELL = re.compile(r"\b(?:sell|sells|selling|sold|pawn|pawns|trade in|trades in)\b", re.IGNORECASE)
_NOT_SELLING = re.compile(
    r"\b(?:don'?t|do not|won'?t|will not|refuse|pretend|if you|would you|how much|"
    r"what would)\b",
    re.IGNORECASE,
)


def sold_item(words: str, held: Sequence[tuple[str, str]]) -> str | None:
    """Which held item the words sell, as its id: ``held`` pairs an item's id
    with its name ("scimitar", "wolf pelt"); the longest name named wins."""
    if not sells(words):
        return None
    lowered = words.lower()
    named = [
        (len(name), item_id)
        for item_id, name in held
        if name and re.search(rf"\b{re.escape(name.lower())}s?\b", lowered)
    ]
    return max(named)[1] if named else None


def sells(words: str) -> bool:
    """The words sell something ("I sell the scimitar to the smith")."""
    return bool(_SELL.search(words)) and not _NOT_SELLING.search(words)


def equip_bought(sheet: Sheet, good_key: str, weapon_keys: Collection[str]) -> bool:
    """Put a bought good to use on a party sheet (in place): a weapon joins
    those it fights with, a shield goes on the arm of a calling trained with
    shields (+2 armour class). True when the sheet changed."""
    if good_key in weapon_keys and good_key not in sheet.weapons:
        sheet.weapons.append(good_key)
        return True
    if good_key == "shield" and not sheet.shield and sheet.character_class in SHIELD_CALLINGS:
        sheet.shield = True
        return True
    return False
