# companions-002: companions who stay with the hero, take orders, and fit the party

## Question

companions-001 left three issues, and checking them turned up a fourth:

1. **Companions ignored the party.** Ash's own decisions knew nothing of the party or the fight.
   Every one of Ash's swings in companions-001 run-5 came from the fallback; on fight turns Ash
   chose to walk to the market, wait, or spar the hero.
2. **The fallback was crude.** It always struck the first foe standing.
3. **Every companion was a fighter.** Ash's card ("Steady stance, weather-worn cloak. Patient,
   dry-witted, dependable. Market ward born and bred.") names no calling, so the keyword match gave
   fighter.
4. **Experience came from rumours the party never touched.** Rumours settle often among others
   (0–2 in a 6-turn scorecard story), and at 50 XP each that was a free level every few story
   days. The dev data has no settled rumour at all (39 open), so this was decided from the
   scorecards.

## What changed

- **The companion note.**
  - A linked companion's decisions and reactions carry it: they travel with the hero's party and
    go where the hero goes.
  - With a fight on, it says which foes stand, in words, and to fight beside the hero, naming the
    foe (`companion_note`).
- **The party travels together.**
  - When the hero moves, a companion standing with them gets the same move (`_follow_hero`).
  - A companion's own move away becomes staying put. Told that they travel with the party, Ash
    still chose the market in run-1, so it is now a rule.
- **Targets and orders.**
  - The fallback strikes the most wounded foe standing.
  - The hero can give orders: a Say to a companion that names a foe ("Ash, take the third
    goblin!") aims that companion's blow that scene (`order_target`).
- **Callings** (from a helper's branch, `application/callings.py`):
  - When someone joins, the small writing model reads their card and the party and picks a race
    and calling, preferring one the party lacks. It falls back to the keywords.
  - The player can change it with `POST /stage1/party/{member_id}/calling` until the companion's
    first fight. The party panel says "Ash joined as a human ranger · Change".
- **Experience:** a settled rumour pays only if a party member is among its people or in the scene
  where it settled (`party_took_part`).

## Live runs

The runs use `companion_check.py` (the companions-001 script plus an order and a walk to the
market) against the dev API on Venice. Each story asks Ash to join, fights goblins, then the hero
walks to the market.

| run | stories | joined | the order | Ash beside Wren at the market | notes |
|---|---|---|---|---|---|
| run-1 | 2 | 2/2 | given after the fight (two goblins fell by turn 3), so untested | 2/2 | Ash's own decisions still chose "move" on fight turns, which led to the stay rule |
| run-2 | 2 | 2/2 | "Ash, take the third goblin!": **Ash struck Goblin 3 both times**, where the fallback would have taken Goblin 2 | 2/2 | three goblins, every fight won |
| run-3 | 1 | 1/1 | — | 1/1 | **Ash joined as a human ranger** (the writing model, $0.000065) |

**What Ash still decides for himself.** Ash's own decisions (Venice) still choose "wait" or
"spar" on fight turns, even with the note. Ash fights anyway:
- his blows in the storyteller's lines now go to him (a line names who swings);
- the fallback acts when he does nothing;
- the hero's orders aim him.

A spar is never a bout while a fight is on.

**Spend:** Venice went from $4.0304 to $3.9219 ($0.1085), and OpenRouter usage from $9.3788 to
$9.3820 ($0.0033: the writing model and moments). That is **$0.112** for 5 stories.

## Follow-up: companions who fight of their own accord, and orders that hold (runs 4–7)

**What was still wrong after run-3**
1. Ash's own choices on fight turns: logged live, Ash chose **spar** every fight turn, not wait.
   The spar-becomes-waiting rule turned that into waiting first, so a companion's own blow never
   happened. The prose showed Ash idle while the fallback's dice had him strike.
2. An order given this turn could not reach Ash's choice for the same turn, since choices are made
   at once. Ash attacked Goblin 2 while told to take the third.
3. A blow at a foe that had just fallen rolled nothing. Wren's "I strike at the second goblin"
   came after Ash had killed it, with Goblin 3 still standing.
4. A storyteller tag smaller than its prose ("Two goblins burst in" under `ENCOUNTER[goblin]`)
   gave one goblin. Goblins seen last turn could not be attacked this turn when no fight was open
   yet.

**What changed**
- **A companion's own choice is a blow while a fight is on.** A spar, wait, look-around or rest
  becomes their attempt ("I attack Goblin 2 with my longsword"), told and rolled.
- **Orders steer and last.** An order steers that companion's blows in the scene it is given, the
  storyteller's tag included. It lasts the fight it was given in (`party_orders` in the world
  config, kept while a foe of that fight remains). The companion's own blow is then chosen at the
  ordered foe.
- **No blow is wasted on the fallen.** A party member's blow aimed at a foe already down goes to
  the most wounded foe standing.
- **The prose sets the count.**
  - An `ENCOUNTER` tag smaller than its prose opens as many foes as the prose says.
  - The prose of the last two turns counts when a fight is opened by the player's words.

| run | code | what it showed |
|---|---|---|
| run-4 | companion choice → blow (wait only) | Ash still recorded "wait": it was the spar that needed converting (a debug log showed spar) |
| run-5 | + spar → blow | Ash's own choices were blows on every fight turn ("I attack Goblin 2 with my longsword"); but the same-turn order went to Goblin 2, and Wren's blow at a fallen goblin was lost |
| run-6 | (the image build failed: Docker Hub timed out; old code ran) | — |
| run-7 | + orders steer and last, re-aim from the fallen (code copied into the running API) | the order sent Ash at Goblin 3 in both stories; next turn Ash's own choice was "I attack the third goblin with my rapier" and it fell; Wren's blow at the second goblin landed; when three goblins dropped both Wren and Ash, both got back up once the fight was over |

**Spend:** Venice went from $3.9219 to $3.7198 ($0.2021), and OpenRouter usage from $9.3820 to
$9.3882 ($0.0062). That is $0.21 for runs 4–7, the debug run and the browser-check story.

**Note:** the dev API image could not be rebuilt at the end (Docker Hub's sign-in timed out), so
the new code was copied into the running container. A plain `docker compose up -d --build api`
rebuilds it properly once Docker Hub answers.
