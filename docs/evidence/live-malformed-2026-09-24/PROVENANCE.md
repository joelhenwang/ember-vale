# Malformed-provider diagnosis — live round 3, 2026-09-24 (UTC)

## Claim

The recurring `malformed` failures are **content-extraction failures at the
provider boundary**, not JSON-parsing, schema-validation, or game-rule
failures: on HTTP 200 with a well-formed envelope, `choices[0].message.content`
is `null` while the model Chairman spent the whole completion budget on
chain-of-thought (`finish_reason: "length"`, `reasoning_tokens` ≈ budget).
The graphs never see these responses — the adapter raises before returning —
so no repair-attempt JSON is ever validated and the existing deterministic
fallbacks engage. JSON parsing, schema validation, and game-rule validation
are never reached for these calls.

A sanitized regression pins the exact shape
(`backend/tests/test_model_diag.py::test_reasoning_only_response_names_the_shape`),
and the adapter now names it: message
`openrouter response carried reasoning but no message text` plus a persisted
`reasoning_only: true` in the call detail. Taxonomy unchanged
(`ModelMalformedError`, no retry, same fallbacks); E3/E6/recovery untouched.

Sustained NPC conversation remains unproven: beat 1 chose WAIT for Ash by
model decision, beat 2's reaction calls (initial + repair) both burned out
as above, and the narrator honestly reported "No answer is given yet".

## Provenance

- Source: working tree at `6121527` (36th push) plus the reasoning-only
  diagnosis (`openrouter.py` message + `reasoning_only` detail flag and its
  regression test), uncommitted.
- API: working-tree source served on `127.0.0.1:18101` against scratch
  database `embervale_live3` (migrated to head `0038_preset_creation_receipt`,
  seeded stage0-v1). Scratch database dropped after the session; user compose
  stack untouched (its `api`/`db` containers kept running).
- UI: `vite dev --port 5174` proxied to `:18101` (temporary `vite.config.ts`
  edit, restored afterwards).
- Pin: openrouter connection with profile revision 2
  (`deepseek/deepseek-v4-flash-0731`, temperature 0.2, max_tokens 4096),
  referenced by the story draft `ai` block. Key read from the local `.env`
  at runtime, never written to evidence.
- Story: Player as Wren with Wren and Ash at Hearth,
  world `3d3cfb40-7140-4a92-88d5-f109d72d5f03`.

## Method notes

- Q1 (beat 1): communicate intent — "Ask Ash what the Market holds today."
- Q2 (beat 2, follow-up): communicate intent — "Ask Ash whether the mill
  wheel will turn tomorrow and what flour he has to spare."
- Both beats driven via the API advance path with player headers; the room
  was opened in headless Edge for the display proof only.
- Audit exported from `model_call` (with `result` detail minus `raw_body`),
  `character_intent`, `attempt`, `reaction`, `resolution`, `narration`.

## Results, by stage

- Provider success: beat 1 — 7/7 calls succeeded (director ×2, decision,
  reaction ×2, resolver, narrator). Beat 2 — 4/6: both `reaction` calls
  (initial + repair) failed `malformed`; decision, resolver, narrator
  succeeded.
- Failed-layer evidence (both beat-2 rows, persisted in `audit.json`
  detail): `http_status` 200, `choices_count` 1, `content_type` NoneType,
  `finish_reason` length, `reasoning_only` true, usage
  prompt ≈2760 / completion 4096 / reasoning ≈4092–4098. The 4096-token pin
  budget was consumed entirely by reasoning; content is null.
- Validated output: both resolutions `outcome: success` via the model
  resolver under the requested pin (profile_version `pin-684991b3-r2`).
  Ash's beat-1 intent validated as `wait` (model decision, not a provider
  fallback); beat-2 reaction unrepairable after its 2 attempts.
- Persisted dialogue: 7 narration rows, zero NPC-spoken lines; the single
  committed reaction is Wren's own WAIT. Beat-2 narration states "No answer
  is given yet; Ash remains waiting."
- Browser display: `room-after-followup.png` shows the follow-up
  ACTION RESOLVED text in Story-so-far with zero page errors.

## Files

- `audit.json` — world id, model-call audit with failure detail, intents,
  attempts, reactions, resolutions, narration.
- `room-after-followup.png` — room feed after beat 2 (follow-up displayed).
