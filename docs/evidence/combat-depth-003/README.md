# combat-depth-003: ability checks, gold coins, and a live level-4 improvement

## Question

long-adventure-002 left three parts of combat stories undone:

1. **Uncertain deeds outside fights** ("climb the wall", "pick the lock") were judged by the storyteller
   alone. In 5e they are ability checks, decided by a die.
2. **Coins from the fallen** were a one-off item called "a few coins", with no count and no use.
3. **The level-4 ability score improvement** was built but never reached in live play.

## What changed

- **Ability checks** (`domain/rules/dnd/checks.py`).
  - A linked party member's free-text attempt that is not a blow or a spell rolls a check when its words
    call for a skill. The skills cover Athletics, Stealth, thieves' tools, Persuasion, Perception,
    Survival, Medicine and nine more, and each uses its 5e ability.
  - The difficulty comes from the words: hard 15 ("steep", "sheer", "guarded"), easy 10 ("low",
    "simple"), otherwise 12.
  - Success when the roll meets the difficulty, partial when it misses by 4 or less, failure otherwise. A
    natural 20 always succeeds and a natural 1 always fails.
  - The roll is seeded by scene and attempt, so a scene that is redone rolls the same.
  - **The resolver hears the roll** ("Dice: Wren's Athletics check: 5 against DC 15, failure…") and the
    outcome follows it (`follow_checks`). The best roll in a scene decides, and the resolver can still
    hold it lower (when the thing reached for is not there).
  - A find (`item_found`) or a settled rumour needs a success.
  - The rolls are kept beside the scene as its dice (`derive_check_event_id`, roll kind `check`). The
    dice view shows "Wren tries Athletics · 5 vs DC 15 · Fails".
- **Gold coins** (`domain/rules/coins.py`, coins-001).
  - A fallen foe that drops no weapon or pelt leaves 2 to 7 gold coins as one counted stack ("Zombie
    left 5 gold coins").
  - Picking coins up, or being handed them, adds them to the purse already carried, so there is one
    stack per holder.
  - A successful attempt that pays ("I pay the innkeeper 3 gold coins", "hand her a coin", "buy bread
    for two coins") takes that many from the purse. They go to the person it is aimed at, or are spent
    when it is aimed at no one. Promises ("if you help"), refusals and pretending pay nothing.
  - The resolver sees purses with their count. It also hears when a payer cannot pay: this run's first
    payment came from empty pockets, and the prose showed coins "glinting in their hand".

## Live run (`live_run.py`, `run-1.json`, Venice)

Wren is a human fighter. As test data, the run set Wren's experience to 2,690, just short of level 4
(2,700).

| turn | Wren's words | dice | outcome |
|---|---|---|---|
| 1 | "I climb the steep wall of the old granary…" | Athletics 5 vs DC 15, **failure** | prose: "the rough surface offers no foothold" |
| 2 | "I search the hearth's woodpile…" | Perception 20 vs DC 12 (natural 20), **success** | |
| 4–7 | seek and fight goblins | a medium fight against a lone goblin, 4 turns; Wren fell to 5/12 HP | Goblin defeated: 200 XP |
| 7 | | **Wren reaches level 2, 3 and 4** (+8 HP each) | "choose a better ability" |
| 8–9 | pick up spoils | none: the goblin left nothing (a 50% chance) | |
| 10 | "I pay Ash 2 gold coins…" | | nothing paid (no purse). This led to the resolver's purse note |

**The level-4 choice in the browser** (`shots/`):
- `2-choice.png`: Character details offers "+2 to one ability or +1 to two".
- `5-picked.png`: +2 Strength picked.
- `6-chosen.png`: the choice is saved and the panel closes.
- The API then read Strength **16 → 18** with no choices left.
- `3-dice.png` shows the three level-ups in the dice.

## Limits

- Coins were not dropped in the live run, so they are covered by tests only (`tests/test_coins.py`):
  merging on pickup, and paying through a full turn.
- Coins have no shop and no prices. Buying is whatever the storyteller makes of a paid attempt.
- Checks are only for party members in combat stories. Ordinary stories keep the resolver's judgement.
- A check needs a skill named by the words. Unmatched attempts ("I mend the axle") are still the
  resolver's call.

## Spend

Venice went from $3.0174 to $2.9295, **$0.088** for both runs (the first stopped at turn 8 on a script
error). Of that, $0.062 is the recorded model cost of the kept story; the rest is the stopped run and
picture-writer calls.
