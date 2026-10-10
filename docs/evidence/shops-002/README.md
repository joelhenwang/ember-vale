# shops-002: a room rests you, a shield guards you, things sell back

## Question

shops-001 left three gaps:
- a room for the night was only paid for;
- a bought shield did nothing;
- nothing could be sold back, not even a fallen foe's spoils.

## What changed

- **A room rests the buyer** (`Good.rests`, `_sleep`): full health, conditions gone, spell slots back,
  stamina and mana full. It is kept as the scene's dice ("Wren sleeps in a room for the night · Rested ·
  Wren 4 → 12"). The story day's own long rest still comes.
- **A shield** goes on the arm of a calling trained with shields in 5e (barbarian, cleric, druid,
  fighter, paladin, ranger), for +2 armour class (`equip_bought`). A wizard who buys one carries it, and
  their armour class stays the same. Fighters, clerics, paladins and barbarians start with one.
- **Selling back** (`sell_price`, `sold_item`, `sell_item`):
  - a place buys back the goods it sells at half price, rounded down, so a one-coin good fetches nothing;
  - a smithy buys a fallen foe's weapon for 3 gold, and a market for 2;
  - a market buys a pelt for 2.
  - The resolver hears what the place buys back, and what a sale fetches ("Market pays 2 gold coins for
    Wren's scimitar", or "Nobody at Hearth buys …").
  - The sale is kept as dice: "Wren sells the scimitar · +2 gold".
- **Adventure:** `GET /stage1/shop` adds `buys`, the things carried that this place buys and their
  prices. The shop strip shows them as dashed "Sell scimitar · 2 gold" chips (`shots/1-sell-chip.png`).

## Live run (Venice, `live_run.py`, continuing shops-001's story at the Market)

As test data, Wren is given a scimitar.

| turn | words | purse | result |
|---|---|---|---|
| 8 | "I sell the scimitar to the trader" | 2 → 4 | "Wren sells scimitar at Market for 2 gold." (the wording is now "sells the scimitar") |
| 9 | go to the Hearth | 4 | |
| 10 | "I rent a room for the night" | 4 → 2 | 12/12 HP and 100 stamina; "wakes rested" |

On turn 10 the dice say only "wakes rested", with no health gain. The turn crossed into a new day, and
that day's long rest had already healed Wren. The line stays honest about it.

Tests (`tests/test_shop_more.py`):
- sale prices, and naming what is sold;
- a shield for a ranger (+2 armour class) and none for a wizard;
- a full-turn story that sells a scimitar at the Market, walks back and pays for a room with the coins.
  The room restores health and stamina, and the dice keep one sale and one rest.

## Limits

- No haggling, and the same prices everywhere.
- Selling takes one of a stack per attempt.
- A meal or ale is still only paid for.

## Spend

About $0.01 on Venice for the 3 turns.
