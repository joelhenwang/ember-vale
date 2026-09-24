# Live player session — 2026-09-24 (UTC)

## Claim

Current-source API + browser UI, story created entirely through the wizard
with a UI-picked provider pin. The pinned profile revision governed every
executed model call. One deliberate Player-as-Wren question traveled the
full pipeline: submitted intent → accepted action → resolution →
persisted narration → browser display.

The live provider returned malformed responses on all 6 calls, so every
model-dependent stage ran its deterministic fallback. Ash's WAIT is a
provider-failure fallback, not a model choice, and no NPC dialogue was
generated. Sustained NPC conversation remains unproven. The narration
milestone stays at **one persisted narration beat**.

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
- Pin: openrouter connection `cc675e59-…`, profile `8e42574d-…` revision 2
  (`deepseek/deepseek-v4-flash-0731`, temperature 0.2), picked on the
  wizard's Art-and-telling step. Key read from the local `.env` at runtime,
  never written to evidence. No mediated payload edits: the pin traveled
  wizard select → draft `ai` save → Review → story setup `art`.
- Story `ee2a5b6d-…` (Player as Wren; Wren and Ash both starting at Hearth;
  archived after the session).

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

- Setup `art` holds the UI-picked pin (`profile_id 8e42574d-…`, revision 2);
  Review rendered `Live Deepseek · deepseek/deepseek-v4-flash-0731 · rev 2`.
- Question beat committed: intent `communicate` validated, attempt
  committed (`Wren says to Ash: Ash, what news from the mill?`),
  resolution `success` via the `deterministic` resolver with rationale
  `fallback: provider failed (ModelMalformedError)`, narration rows
  persisted and matching the visible feed exactly. Timeline: 3 entries
  (`world_seeded`, `world_ticked`, `action_resolved`), no duplicates.
- Provider-call counts (attempts, not successes): 6 attempted, 0
  succeeded — `director`, `character_decision`, `reaction` ×2, `resolver`,
  `narrator`, all under `openrouter@pin-8e42574d-r2`, all failing
  `malformed`. These counts say nothing about interpretation or
  validation, which are recorded separately (intent/attempt statuses).
- No reaction rows: Ash never received the question in any decision
  context (the decision call was malformed), so nothing valid survived
  validation for a reaction — reported as missing, not forced.
- Reload: Player badge, `Playing as Wren`, and the feed survived; no
  duplicate events. No page errors across the session.

## Files

- `transcript.json` — drive checks in execution order.
- `wizard-ai-pin.png`, `wizard-review.png`, `room-ask.png`,
  `room-after-ask.png` — representative screenshots.
- `audit.json` — setup pin, timeline, model-call audit, and the full
  scene trace (intents, attempts, reactions, resolutions, narrations).
- `story-id.txt` — story id for audit correlation (story archived).
