# long-adventure-001: a long combat adventure, played live

## Question

Every combat check so far was a 6-turn story. What does long play look like? This test checks how
often fights come, whether levels arrive, how rest and recovery work over days, and whether
anything breaks over 20 to 30 turns.

## Setup

`long_run.py` runs against the dev API (Venice `venice-uncensored-1-2`). Wren, a human fighter,
invites Ash at the Hearth and then plays a fixed 26-turn plan. A story day is 10 turns, so the plan
spans three days:

- talking and travelling to the market;
- asking after raiders, then looking for goblins and attacking them;
- resting and going back;
- looking for the goblin camp and attacking again;
- searching, reporting at the market, waiting and looking for trouble.

The plan only says what a player would write. Whether foes appear is up to the storyteller and the
engine. `analyse.py` prints each turn: party health, experience and level, foes, rolls, failed
tags, and Ash's own choice.

## Results

| | story 1 | story 2 | story 3 (after fixes) |
|---|---|---|---|
| turns played | 26 | 22, then turns 22–26 on fixed code | 26 |
| fights | **1** (a lone goblin, turn 7) | **1** (a lone goblin, turn 7) | **2** (turn 7, and turn 17 when Wren went looking) |
| experience at the end (each) | 25 | 25 | 50 |
| levels gained | 0 | 0 | 0 |
| rumours settled | 0 | 0 | 0 |
| seconds per turn (median / max) | 11.8 / 18.8 | 11.2 / 21.8 | 10.4 / 14.9 |
| spend | $0.157 | $0.091 (+ the resumed turns) | $0.110 |

**What went right:**
- The night's rest healed: Wren went from 7/12 to 12/12 at dawn on day 2.
- Ash joined, travelled with Wren and fought: his own choice was "I attack Goblin with my
  longsword".
- Turns stayed around 10 to 12 seconds over 26 turns.

## What it found, and what was fixed

1. **A turn failed with a 500 error** (story 2, turn 22, a rest). The error was
   `INVARIANT_VIOLATED "projection left bounds: stamina=110"`, and the run was left half done.
   - **Cause:** Wren's rest was planned from the phase's shared view (stamina 90). An earlier scene
     of the same phase had already brought the row to 100. The request carried fresh versions, so
     it passed the version check, and the stale +10 projected out of bounds before `save_state`'s
     own check could fire.
   - **Fix:** an out-of-bounds projection of an effect planned from an older version is now a
     version conflict. The scene loop already redoes a scene on a version conflict.
     `tests/test_tx_commit.py` reproduces the exact error without the fix.
   - **Check:** the stuck turn then played through, and so did turns 23 to 26.
2. **The player's words could never bring goblins back.** After the first goblin fell on day 1, "I
   attack the first goblin I see" could not open another fight all story. The slain-stay-slain
   guard held forever.
   - **Fix:** the guard now covers only kinds slain in the last fight while it lingers
     (`slain_lately`).
3. **A blow at no creature still rolled.** The storyteller tagged `ATTACK[longsword at enemy]`,
   and the dice read "hits enemy for 9 slashing (0->0 HP)".
   - **Fix:** a party member's blow at something the tables don't know now rolls nothing.
4. **The storyteller ignored a fight being sought.** It narrated "I attack the first goblin I see"
   as a declaration by the hearth.
   - **Fix:** when a party member attacks and no fight is on, the narrator is told the party is
     looking for a fight (`dnd-seek`). It should bring the foes in with `ENCOUNTER[...]` if they
     could be there, or show plainly that none are found.
   - **Result:** story 3 got its second fight on day 2, when Wren went looking.

## What remains (a balance decision)

**Levels are out of reach in long play.** A lone goblin gives 50 XP, shared between two: 25 each.
Level 2 needs 300 XP, which would be about 12 such fights. Over 26 turns there were one or two
fights. No rumour was settled either, so settled-rumour XP never paid. The SRD numbers assume many
fights a day; a story game has a fight every dozen turns. See the session report for the options.

**Fights are small.** The storyteller opens lone, easy goblins, and they fall within a turn or two.

## Spend

Venice went from $3.7198 to $3.3404 ($0.379), and OpenRouter usage from $9.3886 to $9.3969
($0.008). That is **$0.39** for three stories, the resumed turns and the debugging, against a
$0.50 cap.
