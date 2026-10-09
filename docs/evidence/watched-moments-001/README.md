# watched-moments-001: automatic pictures for watched stories (2026-10-09)

**Question.** Key moments were painted only for player stories: the moment rules (the player's arrival, the player's first meeting, the player's scene judged by the writer) all needed a player. A watched story got pictures only when the watcher painted a scene by hand (watch-pictures-001). What should a watched story paint on its own?

**Decision (product choice made under autonomy, owner approved the item).**
- **Candidates:** every narrated scene of a turn, not just the player's.
- **Fixed moments:**
  - a rumour settled anywhere;
  - the first scene any two characters share, once per pair (key `scene:meeting:<a>:<b>` with the ids sorted).
  - Arrivals are left out, because in a watched cast someone is always arriving somewhere.
- **The moment writer** reads up to 3 of the turn's longest scenes (`WATCHED_SCENES_JUDGED`), one call each at about $0.0001, and the most worthwhile scene is tried first.
- **Pace:** at most one picture a turn, and one per 3 turns. Only a settled rumour skips the wait in a watched story. A turning point does not, unlike in a player story: the first live run showed that reading several scenes a turn finds "turning points" often (2 of 6 turns rated 3 for ordinary departures).
- **Player stories are unchanged.**

**Tests** (`tests/test_scene_pictures.py::test_a_watched_story_gets_its_first_meeting_and_turning_points`; it fails on the old code):
- with no player, the first meeting is queued;
- the same pair is never painted twice over 5 turns;
- with a writer, a turning point is queued;
- the next turn's turning point waits out the cooldown;
- everything paints.

The full suite passes.

**Live** (the dev watched story, 6 autoplayed turns on Venice with the local Krea painter):
- With the first rule set, the story got a first meeting ("Waiting by the Path") and two turning points ("Left Beneath the Lanterns", "A Quiet Departure"), each with the writer's headline. That prompted the cooldown rule above.
- The Watch feed marks the four painted scenes, and the event view shows the picture (`1-watch.png`, `2-event-with-picture.png`, `watch-shot.mjs`).
- Spend: $0.033 on Venice (34 calls) plus the writer's few calls (about $0.0003).
