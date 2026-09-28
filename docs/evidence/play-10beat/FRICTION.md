# 10-beat ordinary play: friction log

Session `d5104e8a` (story `Ten beats mul6area`), Player-as-Wren, pinned to
`deepseek/deepseek-v4-flash-0731` rev10 via the creation wizard. Driver
`scripts/play-10beat.mjs`; step results in `results.json`; screenshots
alongside. One follow-up probe beat (11) was committed during diagnosis;
the recorded 10-beat run itself ended at clock 10.

## What worked

- Wizard creation with an explicit pin: provider list, rev10 selection,
  `Selected:` summary, and Review line all named the model; the room
  banner confirms `Storyteller deepseek/… rev 10 (pinned) — live provider
  configured`.
- 10/10 beats committed, no stranded runs, no recovery needed. Reload
  after beat 6 restored the clock (beat 6) and the grant.
- The waiting state renders mid-beat (`waiting.png`): elapsed seconds, the
  server-side-work sentence, and the reload/recovery pointer. No invented
  progress.
- Ash answers questions in the room (beats 2–4, 7–10 carry `Ash: …`
  dialogue in the feed; beat 10 verified structurally, see below).
- Beat 5's fallback is stated on the beat, not hidden.

## Slow

Per-beat waits (85, 226, 195, 316, 170, 25, 231, 240, 416, 296s) total
~37 minutes of waiting for 10 beats. Beat 9 (416s) and beat 4 (316s) are
the tails the comparison arms predicted. Nothing in the room explains the
variance. Beat 6 (travel, 25s) shows beats without question handling can
be quick — the wait tracks provider work, not ceremony.

## Repetitive

Nine questions get short one-line answers; the exchange never builds
beyond Q&A because nothing carries session context forward visibly (a
follow-up that repeats the earlier answer does not establish remembered
context — memory stays a separate claim). Narration is fallback
everywhere in this session's beats per the comparison arms' finding.

## Confusing / dependent

- The choice (beat 5 asked where to head) produced advice that named no
  reachable place, so beat 6 defaulted to the first travel offer
  (Hearth). Reactive play works only when answers name real destinations.
- Wizard `Provider` options load asynchronously; a driver (or a fast
  clicker) that reads them instantly sees an empty list. The play driver
  now waits for the options explicitly.
- Ask and Commit are two paths to one beat: asking files into the beat
  directly (no second click); travel needs Start journey plus Commit.
  The driver first clicked Commit after Ask and timed out — an honest
  first-time-user trap worth one sentence in the setup guide.

## Structured-reading bug found and fixed

The in-run checks recorded `speakers=none` and the reload check failed
(`0 spoken lines`) although answers were present: `BeatEntry` joined the
structured content on the beat's FIRST entry id (the `world_ticked` row)
instead of the resolved event the scene pointer names, so the detail
fetch never fired. Fixed by passing the pointer's event id down
(`detailEventId`); the composable needed no change. Verified with zero
additional spend by seeding the real beat-10 pointer from the duplicate
replay and reloading: Ash's dialogue renders with speaker avatar and an
expandable Beat details section (`rich-beat10.png`). The `results.json`
`speakers`/`fallback` columns from the original run therefore undercount
what the room showed; the snippets in the timeline (queried read-only
afterwards) confirm Ash answered beats 2–4 and 7–10.

## Cost

Within the agreed $5 cap: two 4-beat comparison arms, ~11 session beats,
and a handful of tiny probes — a few hundred thousand tokens total on
cheap flash-tier models. No budget was raised for this milestone.

## Addendum: beat-12 natural-path verification

After fixing the structured-reading join bug, one further beat was
committed through the room UI (story now at clock 12) to verify the fix
on the natural path — fresh profile, no seeded pointers:

- Waiting frames observed live: `Beat 12 is still running — 8s / 33s /
  58s so far`, same honest text throughout, then the notice clears on
  commit. Elapsed time ticks across the wait; nothing else pretends to
  measure progress.
- Post-commit the Beat 12 card rendered Ash's dialogue with speaker
  avatar plus the Beat details disclosure (`beat12.png`) — pointers
  recorded by the commit itself drove the fetch. The beat also carries
  the fallback notice, matching the comparison finding (model-backed
  answers, fallback narration).
