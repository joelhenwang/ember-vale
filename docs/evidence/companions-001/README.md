# companions-001: companions who join, and fight beside the hero

## Question

Companions (`RECRUIT[...]`, party-combat-001) had never been checked live, nor how they behave
now that foes strike back on their own (combat-depth-002). Does a companion join when asked, and
do they fight?

## Setup

`companion_check.py` runs against the dev API (Venice `venice-uncensored-1-2`):

- A new combat story: Wren is a human fighter, and Ash stands beside Wren at the Hearth.
- **Asking:** Wren asks Ash (Say) to "join me as my companion and fight at my side", at most
  twice.
- **Fighting:** once Ash is in the party, four fight turns follow ("Two goblins burst in…").
- **What it reads:** the party after every turn and the stored fight events. Two stories per
  run.

## Runs, the problems found, and the fixes

| run | code | Ash joined | what went wrong |
|---|---|---|---|
| run-1 | before | **0/2** | Ash answered "I'll consider your offer" twice; nothing ever recruited |
| run-2 | invitations + companions help | 2/2 | the hero rolled **0 of 8** fight turns: every "longsword" blow went to Ash, the first longsword carrier on the roster |
| run-3 | + a tag line is the blow of the member it names | 2/2 | Ash, waiting, got a scene of their own and killed the last goblin there before Wren's scene rolled |
| run-4 | + companions help only beside the hero, by place | 2/2 | Ash **sparred** Wren with a goblin standing; the spar took the scene's fight event id and the fight's own dice were lost |
| run-5 | + spars have their own id, no friendly bout mid-fight | **2/2** | none seen |

**What changed**

1. **An invitation is a real choice** (`domain/rules/dnd/invites.py`)
   - The hero of a combat story may invite someone ("join me", "be my companion", "travel with
     me", "fight at my side"…).
   - The invited character's reaction is then told plainly that it must answer now, yes or no.
   - A plain yes ("Yes, I will come", "count me in") makes them a companion at once
     (`_join_invited`). The companion is linked to their own character, with a race and calling
     read from their card (else human fighter), at the party's level.
   - Hedged or conditional answers are not a yes. The storyteller's `RECRUIT` tag still works.
2. **A linked companion's own attacks roll** like the hero's (deeds).
3. **Companions fight beside the hero.**
   - A companion beside the played hero whom nothing had act strikes the first foe standing,
     with their first weapon (a caster uses a damaging cantrip).
   - "Beside" means in the hero's scene, or at the same place.
   - This is counted as `helped` on the fight event.
4. **Only the played hero makes level-up choices** (from the role grant). Companions take
   theirs at once.
5. **A tag line is the blow of the party member its prose names**
   ("ATTACK[longsword at goblin]: Ash lunges" is Ash's). The weapon decides only when no one is
   named.
6. **Spars:**
   - A spar has its own event id (`derive_spar_event_id`). It used to share the combat id, and the
     fight record collided.
   - There is no friendly bout while a fight is on.

## Run 5 (final code)

- **Ash joined** in both stories.
- **Story 1:**
  - Wren and Ash each struck every turn while a goblin stood.
  - Both goblins fell by turn 3.
  - After that, nothing rolled.
- **Story 2:**
  - Two goblins dropped Wren on turn 2.
  - Ash fought on alone, and the goblins turned on Ash.
  - The fight was still on when the script stopped. Wren gets back up once it ends
    (combat-depth-002 follow-up).

## Fight check after the damage, getting-up and group changes

`../combat-depth-002/run-5.json` is one run of the three combat-depth-002 scenarios. It was played
after weapon damage gained the ability bonus, after downed heroes began getting back up once a
fight ends, and after "two goblins" in the words began opening two goblins.

- **All 3 fights won.**
- **9/9 attack turns rolled** where a foe was up.
- **"Two goblins burst in"** opened `ENCOUNTER[2x Goblin]` (Goblin 1 and Goblin 2). The player's
  "I go after the second goblin" hit Goblin 2.

## Spend

Venice went from $4.2599 to $4.0304 ($0.2295), and OpenRouter usage from $9.3721 to $9.3788
($0.0066). That is **$0.236** for the 10 companion stories and the 3-story fight check.

## Left as is

- **Recruiting depends on the invited character's reply** saying yes plainly. A character who
  truly wouldn't come (busy, wary) still says no, which is the point.
- **A companion's class comes from a few plain words in their card.** Ash's card names no
  calling, so Ash is a fighter.
- **Companions strike the first foe standing.** They don't choose targets.
