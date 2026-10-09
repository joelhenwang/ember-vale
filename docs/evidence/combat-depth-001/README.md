# combat-depth-001: each foe its own health, XP and levels, spell slots, the dice in Watch

## Question

The owner approved four steps on top of party combat (`party-combat-001`), in order:

1. each monster in a group has its own health;
2. XP and levelling;
3. spell slots are spent;
4. the dice show in Watch.

Can they be built on the storyteller-driven engine (narrator tags, `resolve_narration_tags`)
so stories without a party behave exactly as before?

## What changed

### 1. Each foe its own health

- `ENCOUNTER[2x goblin]` makes **Goblin 1** and **Goblin 2**, each with its own pool
  (`dnd_monster` keys `goblin-1`/`goblin-2`). A lone foe keeps its plain name and key (`goblin`),
  so old stories and the v1/v2 behaviour still read the same.
- **Targeting** (`foe_name_parts` in `combat_resolve.py`): `Goblin 2`, `goblin #2`, `goblin2`,
  `2nd goblin`, `the second goblin`. A plain `goblin` is the **first of its kind still
  standing** (this scene's foes first, then the fight that is on, then any carried pool by
  number). Foes strike from the standing ones; the fallen do not strike.
- **Fresh or reinforcements.** A fresh ENCOUNTER after a finished fight (nobody of that kind
  standing in the fight that is on) starts fresh at 1. While foes of that kind still stand in
  the fight that is on, newcomers are numbered after them (`Goblin 3`), instead of
  silently respawning the wounded ones at full health.
- The fight event's `foes` are now **the fight that is on plus this scene's foes**. Before,
  only the foes touched in the scene were listed, so a goblin nobody struck this turn dropped off
  the panel and out of the narrator's `dnd-foes` fact.
- Rules prompt **`dnd-rules.v3`** (v1 and v2 kept as files; v1 is the parity text). It adds
  numbered foes (in the tags only; prose stays free), spell slots, and "never state XP or
  levels".
- **No migration**: numbered pools are ordinary `dnd_monster` rows.

### 2. XP and levelling (`domain/rules/dnd/progress.py`)

- A foe that falls in a scene (its pool goes from above 0 to 0) gives the XP its SRD stat block
  lists, by challenge rating (`content/dnd/monsters.json`, goblin 50, orc 100…). The XP is
  **shared evenly by the whole party**, rounded down as in 5e.
- Crossing a 5e threshold (`LEVEL_XP`: 300, 900, 2700…) levels up through `level_up_preview`:
  - HP rises by the average hit die plus CON, never below 1, on both current and max;
  - proficiency and spell slots follow from the new level;
  - spells the class's auto-build would pick at the new level are added to the known ones
    (Wren learned Bane at cleric 2).
  - Several levels at once are taken in turn.
- XP and level live in the party sheet JSON (`Sheet.xp`, `Sheet.level`). No migration.
- **Reads:** `GET /stage1/party` adds `xp`, `xp_level_start` and `xp_next_level`. Each roll gains
  an `xp` row (`amount` total, `share` each, `target` the fallen) and a `level` row (`actor`,
  `level`, `amount` the HP gained).
- **UI:**
  - The party panel shows an XP bar ("310 / 900 XP") and a **"Level up!"** badge
    (`ev-pop-once`) beside the name of whoever levelled in the newest fight. A level gained
    while watching throws sparks (`burst`).
  - The combat level reads "Level 2 Cleric" in the party panel only. The status bar keeps
    journey renown ("Level 1 · Newcomer"); the two systems are not mixed.
  - Under the scene, the dice say "Goblin 1, Goblin 2 are defeated · 100 XP" and "Level up!
    Wren reaches level 2 · +7 hit points". This row pops and sparks when fresh.

### 3. Spell slots are spent

- **CAST of a levelled spell** uses a slot of its level, or the lowest free higher one (upcast:
  the dice scale with the slot). With none left the spell fails plainly, with no roll:
  "Wren has no 1st-level spell slot left: Cure Wounds fails." The reader sees "Wren tries Cure
  Wounds · No spell slot left · it fails". **Cantrips are free.**
- **The long rest is a new story day** (chosen over the `rest` action at night). The sheet
  records `slots_used` on `slots_day`; when the story day changes, the slots are back. This is
  lazy, so no beat hook, migration or checkpoint change is needed, and a branch carries it as
  it stood.
- The narrator gets "Spell slots left today: 0 first-level (cantrips are free)" with each caster's
  sheet, so it can have a dry caster fight another way.
- **Reads:** `spell_slots_left` beside `spell_slots`. The panel says "Spell slots today 1 of 3
  first-level".

### 4. The dice in Watch

- A fight's rolls fold into their scene (`groupFeed` skips a combat event whose scene is
  loaded). A scene with dice carries a small die mark in the feed (`EventFeed`, `fought`). The
  event view shows the scene's dice under its narration, reusing `CombatRolls.vue`
  (`EventModal`, `rolls`; `rollsByScene`/`rollsFor` in `game/observatory.ts`). A fight whose
  scene is not loaded still stands on its own.
- **Found and fixed:** in a fight everyone may only "wait" (the storyteller brings the foes), so
  the feed folded those turns into "A quiet stretch". A turn with dice is now never quiet.

### Also found and fixed: the party's sheets reached scenes the party was not in

Every scene of a party story got the D&D context and the `dnd-sheet:*` facts, and was sent to the
narrator even when quiet. Ash, waiting at the market away from the fight, came out as "Ash waits
[D&D SHEET] Wren - Level 2 human cleric HP 7/17…" in the feed. Now `party_in_scene` passes the
roster only to a scene the linked hero is in. A party begun by hand with no linked member still
counts everywhere, as before. Ash's scene is told like any scene in a story without fights: "Ash
waits", with no model call when quiet.

## Gating

Everything sits behind the party roster: no party, no tags rolled, no fight events, nothing new in
the feed. The new sheet fields have defaults, so old sheets read as "no slots spent, 0 XP". No
story table was added or changed, so the checkpoint/branch copy list is unchanged and
`tests/test_story_branches.py` passes.

## How verified

- **Backend:** ruff, `ruff format --check`, basedpyright (0 errors), `gen_ts_client.py --check`,
  and the full `pytest -n 4` suite: **956 passed, 1 skipped**. New tests:
  - `test_dnd_combat.py` (9): group pools and numbers; every way of numbering; a plain target
    skips the fallen and the fallen do not strike; a fresh encounter after a finished fight;
    reinforcements join a fight that is on; shared XP; levelling (HP 13 to 21, level row);
    slots spent, upcast and "no slot left", back on a new day; cantrips free.
  - `test_party_combat.py` (2): the end-to-end group fight runs through the API with a
    scripted narrator (Goblin 1/2 pools; the third cure fails; Goblin 2 falls; 50 XP; 290 to 340
    XP levels Wren to 2 with a third slot and one left today; both foes stay listed; no "D&D"
    text in any chronicle entry), and `party_in_scene`.
  - Updated: two fireball tests use a level-5 wizard, since a level-3 wizard has no 3rd-level
    slot (DC 13 to 14). The wire replay mirrors the fight that is on.
- **Frontend:** prettier, eslint, vue-tsc, vitest (**476 passed**; 5 new in `party.spec.ts` and
  `observatory.spec.ts`), vite build.
- **Screenshots** (headless Edge, `depth-shots.mjs`, results in `shots/run.json`). The API was the
  worktree on 8103 running `scripted_storyteller.py` (a fake gateway whose narrator tags the
  hero's scene at the Hearth), on a scratch database `embervale_combat2`, dropped afterwards. The
  hero is a human cleric. **`prime_xp.py` set her XP to 260 after creation**, so that one goblin
  (50 XP) crosses level 2 in a short run; every other number was rolled. The dice are seeded per
  event, so they differ between runs.

| Shot | What it shows |
|---|---|
| `shots/1-turn-1.png` | Turn 1: "A fight begins: Goblin 1, Goblin 2", strikes at Goblin 2, two cures, then "Wren tries Cure Wounds · No spell slot left · it fails"; Your party "Spell slots today 0 of 2 first-level", 260 / 300 XP |
| `shots/2-dice-two-goblins-no-slot.png` | The same dice up close |
| `shots/3-party-two-goblins.png` | Party (Character details): Goblin 1 7/7 and Goblin 2 5/7, each with its own bar |
| `shots/4-level-up-turn.png`, `shots/5-dice-xp-level-up.png` | Turn 2: a natural 20 fells Goblin 1, Goblin 2 falls, "Goblin 1, Goblin 2 are defeated · 100 XP", "Level up! Wren reaches level 2 · +7 hit points" |
| `shots/6-party-level-up.png`, `shots/7-character-details.png` | "Level up!" badge, Level 2 Human cleric, 17/17, 360 / 900 XP, "1 of 3 first-level", Bane learned; the status bar still says "Level 1 · Newcomer" (renown) |
| `shots/8-watch-feed.png` | Watch feed: Wren's fight scenes carry a die mark; Ash's market scene reads "Ash waits" |
| `shots/9-watch-event-dice.png` | Watch event view: the turn-1 scene with its dice under the narration |

No tag text was visible anywhere (`tagsVisible: false`). The only console errors are 64 × 403s
from the dev server refusing font files outside the worktree (the `node_modules` junction to
main), not the feature.

## Live check (Venice, `venice-uncensored-1-2`, the provider main's `.env` selects)

`live_check.py` created a combat story (Wren, human cleric) and played three turns against two
goblins ("I attack the first goblin", "I cast guiding bolt at the second goblin", "I swing at
whichever goblin is still standing"). Results are in `live-check.json`.

- The turns took 7.7–9.7 s each.
- The hero's scenes got `dnd-rules.v3` and the slots line; the market scenes got none, as
  designed. This was checked in the stored model calls.
- **The narrator wrote no tags this run**: it narrated the goblins and the guiding bolt in prose
  only, so the engine rolled nothing and no XP or slot changed. `party-combat-001` saw the same in
  one of its runs (v2 before the beat-placement rule), and tags in the others. One run cannot tell
  whether v3's longer rules make tagging less likely or this was variance. **A scorecard-style
  measurement over several runs (v2 against v3) is the next step before relying on live fights.**
- **Spend:** Venice balance $4.7328 before, $4.7234 after, so **$0.0093** (14 model calls,
  41k prompt tokens, 1.2k completion tokens; an upper bound, since other sessions share the key).
  The cap was $0.30.

## Verdict

Shipped in the branch. All four steps work end to end with a storyteller that tags. The engine
side is deterministic and tested. Whether a live narrator tags reliably under v3 is not yet
measured.

## Known gaps

- Live tagging under v3 is unmeasured; this run wrote no tags (see above).
- A hero at 0 HP who levels up in the same scene gets the level's HP back (5e raises current HP
  with max). There is no death or dying rule yet.
- The long rest restores spell slots only. HP and conditions are not restored, and there is no
  short rest or Arcane Recovery.
- XP comes only from foes that fall to tagged rolls. There is no XP for quests or settled rumours,
  and no XP for foes that flee.
- Level-ups add spells by the auto-build's picks; the player does not choose them. Ability score
  improvements (level 4+) are not applied.
- The "Level up!" badge follows the newest fight's rolls, so it stays until the next fight.
