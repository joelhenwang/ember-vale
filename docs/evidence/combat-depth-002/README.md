# combat-depth-002: fights that follow the player, go both ways, and end

## Question

Combat stories (party-combat-001, combat-depth-001) roll dice only when the storyteller tags a
blow. In combat-depth-001 a live narrator under dnd-rules.v2 rolled nothing in one fight out of
three, although the player wrote "I attack the goblin". The owner asked for four things:

1. make fights roll reliably;
2. fix a known bug: a level-up stood a downed hero back up;
3. complete combat: the night's rest heals, and level-ups bring the player's own choices;
4. a live quality check of combat stories, to see where combat needs work beyond item 1.

## What changed

**The player's own words roll** (`domain/rules/dnd/deeds.py`, `Deed`, `deed_lines`)
- A linked hero's interact attempt in the scene is read as a deed.
- If it plainly attacks or casts, and the storyteller did not tag that hero, the game adds the tag
  line itself, after the scene's first ENCOUNTER line.
- **Weapon or spell:** one on the sheet that the words name; otherwise the first weapon that suits
  the verb (shoot/fire/loose take a ranged weapon).
- **Target:** a foe of the fight that is on or of the scene's ENCOUNTER. A numbered foe is taken
  when the words name it ("the second goblin"); otherwise the first foe standing.
- **No fight on:** a creature that both the player and the storyteller's prose name opens one.
- **What does not count:**
  - stand-down words ("lower", "sheathe", "don't");
  - a downed hero;
  - a kind of creature already slain in this story (only the storyteller's ENCOUNTER brings
    another).
- Healing spells aim at a named party member, else the caster.
- The fight event's summary counts the added lines (`deeds`).

**Fights go both ways.** The live checks found that the storyteller almost never tags a foe's blow.
- When the party fought in a scene and no foe's blow was tagged, each foe still standing (up to
  3) strikes once.
- Each strikes at the hero who acted, else at the first party member standing.

**Rules made consistent**
- A hero at 0 HP neither swings nor casts, and the narrator hears that they are down
  (`dnd-down`).
- A blow at a foe already fallen rolls nothing and spends no slot. Before, it rolled
  "hits Goblin for 4 (0->0 HP)".
- A fight that ended within the last turns is told to the narrator as over (`dnd-foes`:
  "The fight is over: Wolf lies defeated…"). Slain foes kept growling in later prose.
- The narrator no longer hears the resolver's verdict on a blow ("it does not work"). The dice
  roll after the prose, and "the spell fizzles" over a hit read as a contradiction.
  - A first try at the wording, "the dice decide", was echoed into the prose, so the verdict is
    now simply left out.
- When narration fails or falls back, the party's own blows still roll.

**Levels and rest** (`domain/rules/dnd/progress.py`)
- A downed hero stays down on a level-up: only the maximum HP grows.
- **Long rest:** a later story day gives full HP, clears conditions and restores slots.
  - It is lazy, on `Sheet.rest_day`.
  - It applies in resolve, spars, the narrator's sheets and `GET /stage1/party`.
  - A sheet that has never woken on a day only learns the day, so old stories do not heal
    mid-day.
- **Ability Score Improvement:** a level that brings one leaves the linked hero +2 to one ability
  or +1 to two (`Sheet.choices`).
- **Spells:** the spells a level brings are picked for the hero and may be swapped.
- Both choices are made with `POST /stage1/party/{member_id}/choices`.
- Unlinked companions take +2 in their class's first abilities at once.
- Adventure shows "A level-up choice is waiting" and a choice panel in Character details
  (`LevelChoices.vue`). A level roll carries `choose`, so the dice say "choose a better ability in
  Character details".

**A bug that predates the session.** An NPC without a sheet chose to spar with the hero. Settling
the bout raised after the scene had committed. The turn stayed half done ("previous phase 3 is
scenes_assembled") and every later turn was refused with 409. A spar without two sheets is now no
bout. The new test fails on the old code.

## Setup

- **Script:** `combat_check.py`, run against the dev API (Venice `venice-uncensored-1-2`, the dev
  `.env` profile).
- **Scenarios:** three, each a new combat story played for 6 scripted turns:
  - a fighter against "two goblins";
  - a wizard (Fire Bolt) against a wolf;
  - a cleric (mace, Sacred Flame, Cure Wounds) against a bandit.
- **What it reads:** the stored fight events (`world_event.summary`) and the chronicle.
- **`analyse.py`:** counts the hero's rolls only on attack turns with a foe still up. It excludes
  turns after the fight was won and turns with the hero down.
- **Code under test in each run:**
  - run-1: deeds, rest and choices (3 stories).
  - run-2: plus foes striking back and slain foes staying slain (6 stories).
  - run-3: plus the spar fix, downed heroes and the verdict left out (6 stories).
  - run-4: plus fight-over and down facts (3 stories).

## Results

| run | attack turns with a foe up | hero rolled | storyteller tagged the hero | from deeds | foe blows | fights won | turns refused |
|---|---|---|---|---|---|---|---|
| combat-depth-001 v2 (before) | 9 | 5 | 5 | — | 0 | 1/3 | 0 |
| run-1 | 14 | **14** | 4 | 10 | **0** | 0/3 | 0 |
| run-2 | 22 | 19 | 12 | 7 | 18 | 3/6 | **7** (spar bug) |
| run-3 | 18 | **18** | 7 | 11 | 14 | 5/6 | 0 |
| run-4 | 9 | **9** | 2 | 7 | 7 | 2/3 | 0 |

- **The hero's blows always roll.** On final code, every attack turn with a foe up rolled: 18/18
  and 9/9. The storyteller alone tagged 9 of those 27 (33%).
- **Run 2's three misses** were all on turns refused by the spar bug.
- **Foe blows** went from none to about one per attack turn.
- **Fights end.** Run 3 won 5 of 6. The sixth, a cleric against a bandit, was still on when the
  script stopped.
- **Prose and dice read together.** The prose now describes attempts without deciding them.
- **Slain foes:** before the fight-over fact (run 3), a slain wolf was "wounded, growling from
  the corner" two turns later. In run 4 the prose reads "stands over the fallen beast".

**Spend.** Venice dropped from $4.6486 to $4.2599 ($0.389), and OpenRouter usage rose from $9.3609
to $9.3721 ($0.011, the moment writer). That is $0.40 in all, against a $0.50 cap. It includes one
aborted run-1 attempt: a chronicle read limit bug, and that story's 6 turns were played.

## What is left (seen, not fixed)

- **A level-1 wizard can fall to one wolf bite** (10 piercing, run-3). With no death or dying,
  the hero lies down until healed or the next story day, and the prose now says so.
- **The storyteller and the engine can disagree on how many foes there are.** "Two goblins" in
  prose with no `ENCOUNTER[2x goblin]` is one goblin to the engine. The player's "second goblin"
  then aims at the only one.
- **Healing at full health still spends the slot,** as the player asked.
- **Two tags in run-3 stayed unresolved.** The raw tags are not stored, only the count.
- **Weapon damage still omits the ability modifier.** Adding it changes many tested numbers and
  balance, so it was left for a decision.
