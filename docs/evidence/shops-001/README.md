# shops-001: something to spend coins on, played live

## Question

combat-depth-003 made gold coins a counted purse that can be paid, but nothing had a price. Shops (the
helper's branch, merged in main) add a catalog, sellers by place, buying through a turn, a healing potion
that heals, and a "For sale" strip in Adventure. None of it had been played live or seen in a browser.

## What exists (from the branch)

- **Catalog:** `content/definitions/shop.json`, 15 goods in whole gold coins, scaled to purses of 2–7
  coins a fallen foe:
  - inn: meal 1, ale 1, room 2, ration 1;
  - market: torch, rope, waterskin, bedroll, healer's kit 3, potion of healing 6, dagger 2;
  - smith: handaxe, spear, shortsword, shield.
- **Who sells:** decided by the place's name (`domain/rules/shop.py`): market/bazaar/stall/shop,
  inn/tavern/hearth, smith/forge/anvil. Only in stories with fights.
- **What the models hear:** the resolver hears what is for sale and at what price, and when a purse is
  short.
- **Buying:** a successful buying attempt for a good sold where the buyer stands takes the price and puts
  the good in hand. A short purse changes nothing.
- **Healing potions:** drinking one heals 2d4+2, kept as the scene's dice (roll kind `potion`).
- **Adventure:** `GET /stage1/shop` feeds a strip above the composer, "For sale at Market · you carry N
  gold". Each chip fills a Do attempt; goods you cannot afford are greyed.

## Live run (Venice, `live_run.py` + `live_more.py`)

A human fighter, Wren, at the Hearth. As test data, Wren starts with 8 gold coins and hurt to 4/12 HP.

| turn | words | purse | result |
|---|---|---|---|
| 1 | "I buy a hot meal from the innkeeper." | 8 → 7 | meal paid |
| 2 | "I rent a room for the night." | 7 → 5 | room paid |
| 3 | go to the Market | 5 | |
| 4 | "I buy a potion of healing." (costs 6) | 5 → 5 | **refused: too little gold**, no change |
| 5 | "I drink the potion of healing." | 5 | nothing to drink |
| 6 | (+3 coins, test data) "I buy a potion of healing." | 8 → 2 | potion in hand |
| 7 | "I drink the potion of healing." | 2 | **"Wren drinks a potion of healing · Healed 4 · Wren 4 → 8"**; the potion is gone |

`shots/1-adventure-shop.png` and `shots/2-phone-shop.png` show the strip at the Market with 2 gold:
chips priced 1–2 gold are live, and the healer's kit and the potion are greyed. The prose and the
illustrated moment showed Wren drinking the potion.

## Limits

These are left undone by design, and are listed in CLAUDE.md §3.14:
- no selling back, no haggling, the same prices everywhere;
- the shield does not raise AC;
- a meal or a room is only paid for, and has no rest effect.

## Spend

$0.017 for the first 5 turns, plus about $0.007 for the last 2 (Venice).
