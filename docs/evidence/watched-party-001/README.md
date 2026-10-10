# watched-party-001: a watched adventure, played live

## Question

The watchparty branch lets an Observer story be "An adventure with fights": the first four cast
members form a linked party, and no one plays them. It was built and tested with fake models only.
Live, does an all-AI party go looking for trouble, do fights start, and do the members fight
together?

## Setup

`live_run.py` creates a watched adventure with Wren and Ash, both at the Hearth, and advances it as the
watcher. All runs used Venice as the storyteller. The writing model picked the callings: Ash a human
fighter, Wren a human bard.

## Results

| run | code | turns | what happened | fights |
|---|---|---|---|---|
| 1 | as merged | 14 | one talk and one walk to the Market, then **both waited 9 turns running** | 0 |
| 2 | + a leader | 14 | Ash leads: 4 moves together, both waiting only 4 turns | 0 |
| 3 | + "trouble may find them" note after 6 quiet turns | 16 | the note reached the storyteller on turns 6–16; it brought no foes, and the pair talked in circles about "the empty stalls" | 0 |
| 4 | the note made firm | 12 | still no ENCOUNTER from Venice (it writes only grounded prose that cites its facts) | 0 |
| 5 | **the engine picks the foes** | 12 | turn 6: wolves come; both members fight side by side for 7 turns, the leader's target followed; **both reach level 2** with no choice left waiting | 1 (4 wolves; Venice wrote two `ENCOUNTER[2x wolf]` lines) |

## What changed (after the merge)

- **A leader** (`watched_leader`: the first linked member).
  - The leader's note: "You lead an adventuring party … you choose where it goes and what it takes on
    … Decide and act; waiting for the others to decide gets nobody anywhere."
  - The others are told who leads and to act rather than wait.
  - When the leader moves, the members standing with them go too (`follow_leader`, after decisions).
  - A follower's own move away becomes staying put, as a played hero's companion's does.
  - A Director or God's directed intents are never overridden.
- **Trouble finds a quiet party.**
  - After `TROUBLE_AFTER` (6) turns with no fight, `trouble_foes` picks one of the common foes at a fair
    size for the party's levels. The pick is seeded by story and turn.
  - The storyteller is told who arrives (`dnd-seek`: "trouble finds them in this scene. Two wolves come
    at them … open it with ENCOUNTER[2x wolf]").
  - If its prose leaves the tag out, the dice open that same fight anyway (`_trouble`, in
    `_resolve_combat_tags`).
  - Played stories are unchanged: there, the player asks for fights.
- **Watch's party panel** no longer caps its height. At 200 px it hid the foes behind a scroll inside
  the panel; now the panel shows in full and the map and feed keep a full screen below it
  (`shots/1-watch.png` before, `3-watch-fixed.png` and `5-phone-fixed.png` after).

## Limits

- The members still talk in circles between fights (run 3: "asking the townsfolk about the empty stalls"
  eight times). The repeat guard does not catch paraphrases, and the director made no rumour they took
  up.
- Venice opened four wolves (a deadly fight for a level-1 pair) by writing the tag twice. They won.
- Nothing here was measured on deepseek through OpenRouter.

## Spend

Venice went from $2.9295 to $2.4587: **$0.471** for the five runs (68 turns). OpenRouter usage went
from $9.7620 to $9.7765 ($0.015: callings and moment captions).
