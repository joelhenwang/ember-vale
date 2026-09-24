# Malformed-provider diagnosis — live round 3, 2026-09-24 (UTC)

## Claim (corrected)

The `audit.json` in this directory contains **12 model calls: 10 succeeded,
2 failed** — beat 1 went 7/7, beat 2 went 3/5. An earlier report of 4/6 for
beat 2 was an arithmetic error; no audit row is missing. Beat attribution
below is positional (first 7 rows beat 1, remaining 5 beat 2): the export
carries no call IDs or phase/run associations. Future exports must include
call id, phase_run_id, task_run_id, actor_id, and created_at per row so beat
attribution is explicit instead of positional.

The confirmed cause below covers **these two failed `reaction` calls**:
a **content-extraction failure at the
provider boundary**, not JSON-parsing, schema-validation, or game-rule
failure. On HTTP 200 with a well-formed envelope,
`choices[0].message.content` is `null` while the model spent the whole
completion budget on chain-of-thought (`finish_reason: "length"`,
`reasoning_tokens` ≈ budget). The graphs never see these responses — the
adapter raises before returning — so no repair-attempt JSON is ever
validated and the existing deterministic fallbacks engage. Earlier
`malformed` responses (previous rounds) predate the persisted detail and
their layer is not established by this evidence.

A sanitized regression pins the exact shape
(`backend/tests/test_model_diag.py::test_reasoning_only_response_names_the_shape`),
and the adapter now names it: message
`openrouter response carried reasoning but no message text` plus a persisted
`reasoning_only: true` in the call detail. Taxonomy unchanged
(`ModelMalformedError`, no retry, same fallbacks); E3/E6/recovery untouched.

Sustained NPC conversation remains unproven for two distinct reasons:
(1) beat 1's reaction answer was lost to the placeholder-target rejection
traced below (plus Ash's decision intent was WAIT); (2) beat 2's reaction
calls both burned out as reasoning-only responses. The
narrator honestly reported "No answer is given yet".

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
  reaction ×2, resolver, narrator). Beat 2 — 3/5: both `reaction` calls
  failed `malformed`; decision, resolver, narrator
  succeeded. 10 of 12 overall.
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

## Beat-1 trace: the lost communication response

Beat 1 produced a schema-valid `communicate` reaction output
(`topic: "Market happenings"`, `target_character_id:
00000000-0000-0000-0000-000000000001`) that was never persisted: the only
committed reaction is Wren's own WAIT.

- Actor: Ash's reaction slot (reacting to Wren's committed question), by
  call order (reactors run per attempt in order: Ash reacts to Wren's
  attempt first, Wren to Ash's second) and topic fit. Attribution is
  circumstantial — the export carries no actor_id; see the Claim note.
- Prompt context: Ash's perspective (names only, no UUIDs) + observable
  summary "Wren says to Ash: …" + the JSON schema demanding a UUID target.
  No valid target ID was ever shown to the model.
- Validation: schema PASS (no repair call exists — beat 1 holds exactly 2
  reaction rows). Repair skipped: the repair budget covers schema
  `ValidationError` only.
- Exact rejection: `precheck_action` denied the output —
  `precheck rejected the reaction (unknown target:
  00000000-0000-0000-0000-000000000001)` — and the graph returned
  `no_reaction` with nothing persisted. The reason lived only in transient
  graph state.
- Root defect: the prompt demanded UUID references it never supplied, so a
  compliant answer was impossible and the model's placeholder was correctly
  rejected. Fix: the reaction prompt now renders a `known_characters`
  name→id roster covering exactly the validated set, wired from the
  orchestrator's existing `names` map. Identity and game-rule validation
  are unchanged — placeholder targets are still rejected with the exact
  reason above. Regressions:
  `test_prompt_lists_known_character_ids_for_targets` (roster supplied and
  target accepted at the proposal level — it asserts the graph proposal,
  not durable persistence; persistence to be verified in a live run) and
  `test_placeholder_target_rejected_with_exact_reason` (pins the
  intact rejection, one call, nothing persisted).

## Files

- `audit.json` — world id, model-call audit with failure detail, intents,
  attempts, reactions, resolutions, narration.
- `room-after-followup.png` — room feed after beat 2 (follow-up displayed).
