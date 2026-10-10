# long-adventure-002: faster fight turns, fair fights, spoils, and the first level-ups

## Question

long-adventure-001 left four things to do:

1. Fight turns were the slowest. A party story narrated scene by scene, inside the turn.
2. The storyteller opened lone goblins: easy fights, over in a blow.
3. Fallen foes gave nothing but experience.
4. Levels were out of reach. The owner chose 4x story-paced experience
   (`WORLDSIM_APP__XP_SCALE`).

This run tests the changes in long live play, and checks the first real level-up in the browser.

## What changed

- **Faster fight turns.** A party story's scenes are narrated side by side. Only their dice and
  recruits wait, rolled in scene order after all the words. With background narration all of it
  lands behind the turn. The turn's checkpoint, and a midnight's day-end, are kept after the fights
  are rolled.
- **Fair fights.**
  - While no fight is on, the storyteller hears how large a fair fight is for this party
    (`dnd-fair`): "two at level 1 … about two goblins, two wolves, three bandits or two skeletons".
  - That alone did not change what it opened: story 1 and story 2 still got lone goblins. So a
    one-kind ENCOUNTER that 5e rates trivial or easy for the party now grows to the largest fair
    count (medium or hard; `WORLDSIM_APP__FAIR_FIGHTS`, default on).
- **Spoils.** A fallen foe may leave what it fought with ("Goblin 1 left a scimitar"), a pelt for a
  beast, or a few coins. Each drops by chance, at most two a scene. They lie where the foe fell, as
  items to pick up.
- **Level-up fixes found in the browser check:**
  - spell swaps keep to the picked spells' own levels (no cantrip for Bane);
  - one spell reads "Keep it, or pick another";
  - a combat story calls the journey level "Renown", so it no longer sits beside the party's
    "Level 2 Cleric" as a second "Level".

## Results

The runs use `long_run.py` (the long-adventure-001 plan, with the hero's calling as an argument)
against the dev API on Venice.

| story | code | fights | experience at the end | levels | spoils |
|---|---|---|---|---|---|
| 1 fighter | before fair sizing | 2, lone goblins | 200 each | none | "Goblin left a scimitar" (Ash picked it up) |
| 2 cleric | before fair sizing | 2, lone goblins | 200 each | none | "Goblin left a scimitar" |
| 3 cleric (`run-2.json`) | fair sizing on | **2, "2x Goblin (hard)"** | **400 each** | **both to level 2 on day 2** (Wren 17 HP, Ash 20 HP) | "Goblin 1 left a scimitar", "Goblin 2 left a scimitar" |

- **Fights now matter.** Story 3's fights lasted 2 to 3 turns. The cleric fell to 5/10 before
  winning.
- **Turn time.** The server's own turn time for these party stories was a median of **5.6 s** (max
  11 s), from the API's phase timings. Narration now takes 0 ms inside the turn. In long-adventure-001
  the script's measured turn was 11 to 12 s, with narration inline.
  - The script still measures about 11.6 s, because it plays the next turn the moment one returns.
    The next turn then waits for the previous turn's words and dice.
  - A player reading the story in between doesn't wait for them.

## The level-up in the browser

Screenshots are in `shots/`, taken with `levelshots.mjs` (Playwright and Edge).

- The party row showed "Wren Level 2 Cleric, 17/17, 400 / 900 XP, Spell slots today 3 of 3
  first-level", and "A level-up choice is waiting".
- The dice showed "Level up! Ash reaches level 2 · +8 hit points" and "Level up! Wren reaches
  level 2 · +7 hit points · choose new spells in Character details".
- Character details showed the spell choice: Bane kept, with others to swap. That is where the
  three fixes above came from (`level-up-choice.png` is after the wording and Renown fixes).

## Spend

Venice went from $3.3404 to $3.0174 ($0.323), and OpenRouter usage from $9.3974 to $9.4061 ($0.009).
That is **$0.33** for three 26-turn stories.
