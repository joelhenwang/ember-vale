# Live player session — 2026-09-24 (UTC)

## Claim

Current-source API + browser UI, story created entirely through the wizard
with a UI-picked provider pin. The pinned profile revision governed every
executed model call. One deliberate Player-as-Wren question traveled the
full pipeline: submitted intent → accepted action → resolution →
persisted narration → browser display.

Round 1 ran against a provider returning malformed responses on all 6
calls, so every model-dependent stage ran its deterministic fallback.
Round 2 (after the beat-budget fix) had 4 of 8 calls succeed, yet
resolution still fell back and no reaction persisted. In both rounds
Ash's WAIT is a failure fallback, not a model choice, and no NPC
dialogue was generated. Sustained NPC conversation remains unproven.
The narration milestone stays at **one persisted narration beat**.

## Provenance

- Source: `6c5f9fa` plus the uncommitted working tree of this task (wizard
  pin picker, pinned interpretation runtime, queue visibility, player-action
  control, and their tests).
- API: working-tree source served on `127.0.0.1:18101` against scratch
  database `embervale_live2` (migrated to head `0038_preset_creation_receipt`,
  seeded stage0-v1). Scratch database dropped after the session; user
  compose stack untouched.
- UI: `vite dev --port 5174` proxied to `:18101` (temporary
  `vite.config.ts` edit, restored afterwards).
- Pin (recreated per round on the fresh scratch database): openrouter
  connection with profile revision 2 (`deepseek/deepseek-v4-flash-0731`,
  temperature 0.2), picked on the wizard's Art-and-telling step each
  round. Key read from the local `.env` at runtime, never written to
  evidence. No mediated payload edits: the pin traveled wizard select →
  draft `ai` save → Review → story setup `art`.
- Stories, both Player as Wren with Wren and Ash starting at Hearth:
  round 1 `ee2a5b6d-…` (pin profile `8e42574d-…` rev 2), round 2
  `e1137d7b-…` (pin profile `83163eb1-…` rev 2, same model and
  temperature). Scratch database dropped after the session.

## Method notes

- New product surface exercised: AI-step provider/profile selects with
  newest-revision default, Review Storyteller row, and the room's Speak-as
  control (target defaults to a co-located castmate; attempt files with the
  next committed beat).
- The ask flow needed no seat mediation: the wizard-created Player grant
  bound Wren, and the seat stayed bound throughout.
- Direction interpretation now resolves the story pin and audits each call
  as a `model_call` row; clarification items remain listed. Neither was
  filed live this run (the bound player seat holds the operator seats);
  both are covered by `test_interpret_runtime.py` and the new queue tests.

## Results

- Setup `art` holds the UI-picked pin each round; Review rendered
  `Live Deepseek · deepseek/deepseek-v4-flash-0731 · rev 2` both times.
- Question beat committed both rounds: intent `communicate` validated,
  attempt committed (`Wren says to Ash: Ash, what news from the mill?`),
  resolution `success` via the `deterministic` resolver, narration rows
  persisted. Timeline: 3 entries (`world_seeded`, `world_ticked`,
  `action_resolved`), no duplicates. Round 1's room feed missed the
  question event (mid-beat refresh race, see below); round 2's feed
  shows it and matches the persisted narration exactly.
- Provider-call counts are attempts, not successes, and say nothing
  about interpretation or validation (recorded separately as
  intent/attempt statuses). Round 1: 6 attempted, 0 succeeded, all
  `malformed` under the requested pin. Round 2: 8 attempted, 4
  succeeded — see the round sections and `audit*.json`.
- No reaction rows: Ash never received the question in any decision
  context (the decision call was malformed), so nothing valid survived
  validation for a reaction — reported as missing, not forced.
- Reload: Player badge and `Playing as Wren` survived both rounds with
  no duplicate events. Round 2's reloaded feed holds all 3 timeline
  entries; round 1's reload count of 2 was taken in the same unsettled
  post-retry state and its feed assertions are superseded by round 2's
  hardened checks. No page errors across either round.

## Files

- `transcript.json` — round-2 drive checks in execution order
  (`transcript-round1.json` is the first round).
- `wizard-ai-pin.png`, `wizard-review.png`, `room-ask.png`,
  `room-after-ask.png` — round-2 screenshots (`*-round1.png` are round 1).
- `audit.json` — round-2 setup pin, timeline, model-call audit, and the
  full scene trace (`audit-round1.json` is round 1).
- `story-id.txt` — round-2 story id for audit correlation.

## Round 1 (kept for the defect it exposed)

The first run passed its DOM assertions but the screenshots showed two
real defects the assertions missed:

- A raw red banner, `phase:1 is already executing`, over a beat that was
  actually committing. Root cause: the shared 30s fetch budget times out
  every slow live beat, and the blind same-index retry lands
  mid-execution as a 409, surfaced verbatim.
- The room feed showed only `WORLD TICKED` / `WORLD SEEDED`: the
  post-beat refresh paged the timeline before the beat's own event
  committed, then read story detail after it — detail said beat 1, feed
  missed the question. Provider counts that round: 6 attempted, 0
  succeeded (all `malformed` under the requested pin).

## Round 2 (client fix, re-verified)

- `useStory.advance` now sends a 10-minute beat budget instead of the
  30s default, so slow live beats return their real report instead of
  timing out into a duplicate POST.
- An already-executing 409 now reports an info notice in plain words
  (naming the filed attempt when one was filed) instead of the raw
  precondition string.
- Re-ran the full drive with hardened checks (question text in feed, zero
  error banners, composer cleared): all pass. The feed shows the
  `ACTION RESOLVED` event with Wren's question, and all 3 timeline
  entries survive reload.
- Provider counts this round: 8 attempted, 4 succeeded (resolver,
  narrator, and one reaction call succeeded; director, decision, and one
  reaction call were `malformed`). Resolution still fell back to the
  deterministic resolver (`unrepairable resolver output (2 attempts)`),
  zero reaction rows persisted, and Ash waited — so sustained NPC
  conversation remains unproven even with live calls succeeding.
