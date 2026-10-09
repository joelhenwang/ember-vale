# party-combat-001: a story with fights, the party panel, and the dice under each scene

## Question

Can a player opt a story into fights, see their party and foes, and read
every roll under the scene it belongs to, while the storyteller-driven engine
stays in charge? The engine is the narrator's `ENCOUNTER/ATTACK/CAST/CONDITION/RECRUIT`
tags rolled by `resolve_narration_tags`, with no turn order or initiative.
Does a real narrator write the tags?

## What changed

Backend:
- **Opt-in per story.** The draft takes `mode.adventure {race, character_class}`.
  It is allowed only for player stories and is checked against `content/dnd`
  (9 races, 12 classes). The hero's level-1 5e sheet (`auto_sheet`) is added
  inside the atomic, idempotent story create and linked to the played
  character, so a failure leaves no half-made story. A draft without the
  choice hashes exactly as before, so old idempotency receipts still replay.
- **Foes strike back.** `ATTACK[goblin at Wren]` rolls the monster's first
  weapon action (its own to-hit and damage) against the hero's AC. Before
  this, only party sheets could attack, so the hero never lost a hit point to
  a monster. A fallen foe cannot strike. A foe first met mid-fight gets a
  pool, so the next scene and the panel know it.
- **Rolls are kept in parts.** Each roll stores actor, target, weapon or
  spell, d20 and total, AC or DC, result, damage and health before and
  after. The combat event's `summary` holds `rolls` (JSON), `scene_event_id`
  and the fight's `foes`. Recruits are listed, and spars use the same shape.
  No migration was needed (`world_event.summary` is JSONB).
- **Reads.** `ChronicleEntry.combat` carries `{scene_event_id, rolls[]}`.
  Fights from before this change fall back to their audit lines.
  `GET /stage1/party` now adds race, AC, weapons, spells and spell slots per
  day, plus `foes` (the latest fight's foes with live HP while it is on:
  rolled in the last 2 turns and someone still standing) and `fight_index`.
  The presentation is unchanged, so the poll fingerprint needs nothing new.
- **Tags never reach a reader.** Narration, chronicle, timeline snippets and
  picture prompts pass through `strip_combat_tags`.
- **Narrator rules `dnd-rules.v2`** (v1 is kept for the monolith parity test):
  - always "at <target>";
  - foes strike by name;
  - each tag starts its own JSON beat, cited to the actor's sheet;
  - an untagged fight does not happen;
  - the dice roll after the prose, so the narrator describes the attempt and
    never decides whether it lands (v1 told it to narrate results it could
    not know).

  A new `dnd-foes` fact tells the narrator, in words and never numbers, which
  fight is on ("Orc (wounded)"), so it does not ENCOUNTER the same foes again.
  Doing so would respawn them at full health.

Frontend:
- New Story, Play mode (player only) offers two choices: **"A tale"** (no
  dice, the default) and **"An adventure with fights"**. The second shows
  people and calling chips, each with a one-line description. The side panel
  and Review show the choice in one line.
- Adventure shows the party in two places:
  - **Your party** above the story lead: hero first, then companions, each
    with level and calling, a health bar with numbers, AC and conditions. An
    "In a fight" badge and **Foes** with their health bars appear while a
    fight is on.
  - The full version in Character details adds weapons, spells and spell
    slots a day.

  The status bar gains a Health bar. A blow that lands shakes the card it
  hurt, and healing makes it glow (`shake`/`flash` from `useEffects`).
- **The dice** sit under each scene and can be folded. Each roll shows a d20
  badge (a natural 20 is filled in ember, a natural 1 is dashed red), who
  attacked whom with what, the total against AC or DC, the result, damage,
  and health before and after. Heals, saves and recruits are shown the same
  way. A fresh critical hit throws sparks (`burst`), and a fresh hit on the
  party jolts the card.
- The party is read with the character sheet, only when the story stamp
  changes. The stamp now includes the newest event, so rolls that land after
  the scene is told still appear.

## How verified

- Backend: `ruff check`, `ruff format --check`, `basedpyright` (0 errors),
  `gen_ts_client.py --check`, and the full `pytest -n 4` suite, green.
  7 new tests:
  - `test_dnd_combat.py`: foe strikes, fallen foes, rolls in parts.
  - `test_party_combat.py`: tags stripped; only a played story with a known
    hero can fight; the end-to-end story test (create, then advance with a
    scripted narrator, then rolls under the scene, narration without tags,
    party and foes, and the next turn's narrator hears "A fight is on with:
    Goblin"); and the foe helpers.
- Frontend: `prettier`, `eslint`, `vue-tsc`, `vitest` (467 passed, 10 new in
  `party.spec.ts`, `adventure.spec.ts`, `drafting.spec.ts`) and `vite build`.
- Screenshots: headless Edge (`combat-shots.mjs`) against the worktree's API
  on 8103. The API ran `scripted_storyteller.py`, a fake gateway whose
  narrator writes tags for the hero's scene: turn 1 is an orc that strikes
  twice, turn 2 is Brann recruited with sacred flame and cure wounds, and
  turn 3 is the follow-up. The database was a scratch copy
  (`embervale_combat`, dropped afterwards). The dice are seeded per event, so
  they differ between runs. `shots/run.json` is the run shown here.

| Shot | What it shows |
|---|---|
| `shots/1-new-story-fights.png` | Play mode: "A tale" or "An adventure with fights", people and calling |
| `shots/2-review.png` | Review row: "An adventure with fights: Wren is a Human fighter, level 1" |
| `shots/4-turn-1.png` … `4-turn-3.png` | Scenes with their dice; Your party with "In a fight" and Foes |
| `shots/5-dice-turn-1.png`, `6-dice-turn-2.png` | The dice up close (miss, hit, foe's greataxe, sacred flame save, heal, recruit) |
| `shots/7-party-block.png` | Party block: Wren 12/12, Brann 10/10, Orc 5/15 |
| `shots/8-character-details.png` | Full party in Character details (weapons, spells, slots a day) |

No tag text was visible anywhere on the page (`tagsVisible: false`), and the
browser logged no errors.

## Live check (Venice, `venice-uncensored-1-2`, the provider the dev `.env` selects)

`live_check.py` creates a combat story and plays three "attack the goblin"
turns.

| Run | Rules | Tags written | Rolled |
|---|---|---|---|
| `live-check.json` | v2 before the beat placement rule | **0**: the narrator wrote only prose | nothing |
| `live-check-2.json` | v2 as committed (tags start their own beat, untagged fights do not happen, `dnd-foes` fact) | 2 × `ATTACK[longsword at goblin]` | Goblin 7 → 1 → 0 |

The first run shows that without the beat placement rule, a real narrator
ignores the tag instructions at the end of the user prompt. The second run
rolled. It still skipped `ENCOUNTER` (the goblin was implied by the attack)
and wrote "the blade bites deep" before the dice. The rules say not to;
treat this as a model limit to watch.

Spend: Venice balance $4.7760 before and $4.7546 after, so **$0.021** for
both runs (an upper bound, since other sessions share the key). The cap was
$0.30.

## Verdict

Shipped. Combat is opt-in per story, and stories without it look and run
exactly as before. The panel and the dice read from what the engine already
records, plus the parts it now keeps.

Known gaps:
- One pool per monster name: `ENCOUNTER[2x goblin]` is one goblin's hit
  points (this is how the engine already worked).
- Weapon damage rolls the weapon's dice without the ability modifier, which
  the monolith port also does.
- Spell slots are shown per day but not spent.
- No XP or levelling.
- The Observatory and story room show the rolls only as the chronicle line.
- Whether the narrator tags reliably needs a scorecard-style measurement over
  several runs before anyone relies on it.

## After the merge into main (2026-10-09)

`live_check.py` ran against the rebuilt dev API (Venice) on merged main (`e3f6fc2`):
- 3 turns of 10–17 s;
- the storyteller started a goblin fight;
- the engine rolled `Wren hits Goblin for 2 slashing (7->5 HP)` and `Wren misses Goblin (8 vs AC 15)`;
- no tags showed in the prose.

Results are in `live-check-main.json`. Adventure (`shots/9-live-main.png`, `adv-shot.mjs`) shows "Your party" with the "In a fight" badge, the goblin at 5/7, "The dice" under the scene, and a key-moment picture of the fight, with no page errors.
