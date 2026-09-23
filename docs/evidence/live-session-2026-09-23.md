# Live narration session — 2026-09-23 (sanitized)

First live-provider session on the configured stack. No credentials recorded;
all key handling stayed server-side in local `.env` (gitignored).

## Configuration

- Profile: `active:openrouter` (`/health/ready`, status `ready`).
- Model: `google/gemma-4-26b-a4b-it:free`, base `https://openrouter.ai/api/v1`.
- Key validity: OpenRouter `/models` returned 200 with this key, so auth works
  and the model id resolves (routed to Google AI Studio).

## Method

API-driven session mirroring the manual path in `docs/alpha-setup.md` §3–§4:
observer (`watcher`) story on builtin Ember Vale/Wren/Ash presets, Wren
Hearth→Market travel, beats 1–3, Director seat + interaction direction
("Ash greets Wren at the Market …"), beat 4, reload/resume. Two full runs
(~2 min apart); test stories archived afterwards.

## Per-beat results

| Run | Beat | Latency | Model runs (profile/status) | Narration |
|-----|------|---------|-----------------------------|-----------|
| 1 | 1 | 12.1s | 3× `openrouter@chat-v1` / failed, 0 tokens | fallback `attempt:wait` only |
| 1 | 2 | 6.2s | 2× failed, 0 tokens | fallback only |
| 1 | 3 | 6.0s | 2× failed, 0 tokens | fallback only |
| 1 | 4 (directed) | 10.7s | 3× failed, 0 tokens | fallback only |
| 2 | 1–4 | 13.3/7.7/6.6/10.6s | same pattern, 10 more failed | fallback only |

Zero runs used the fake profile; zero runs succeeded. `model_call` rows for
both worlds: 20/20 `status=failed, error_code=rate_limited`, ~4.5s each.

Upstream cause (direct probe, same key/model): HTTP 429,
`"<model>:free is temporarily rate-limited upstream … limit_source:
upstream_provider_shared_pool"`. The free shared pool is throttled for this
key; generations never reached the provider.

## State consistency (proven under the live profile)

- Travel resolved: map shows Hearth empty, Market occupied by both Wren's
  and Ash's instance ids.
- Beats committed cleanly (indices 1–4), timeline grew (total 14), reload
  re-read `absolute_index=4`, day 1, phase afternoon.
- Director direction filed and returned `needs_clarification`, matching the
  documented expectation; the beat still committed around it.

## Second model: qwen3.8-27b (same day)

Switched `WORLDSIM_PROVIDER__OPENROUTER_MODEL` to `qwen/qwen3.8-27b:free`
(picked live from `/models`; 21 free models listed) and reran the same
session. Result: 8× `rate_limited`, 2× `malformed`, still fallback-only
narration. Direct probes of the qwen model (plain, story-like, and
`json_object` modes) all returned the same upstream 429 from its shared
pool, so the two `malformed` rows were likely load-shedding 200s with
empty choices, not usable prose. Test story archived.

## Third model: deepseek-v4-flash-0731 (same day, paid)

Maintainer-named model; verified on `/models` first ($0.04/M prompt,
$0.64/M completion). Session cost ≈ $0.003 (8,851 prompt + 4,193
completion tokens); total spend incl. probes ≈ $0.005.

Result per role (`model_call`): character_decision 3 succeeded / 6
`malformed`; director 2 succeeded / 1 `malformed`. The 2 director
successes carried ~4k completion tokens — prose-shaped output under
`json_object` mode that could not validate. All 8 committed intents are
validated WAIT (including deterministic fallbacks), so the narrator had
nothing to narrate: still zero live prose.

Control probe with the exact versioned character system prompt and
representative Wren context returned perfect schema JSON (a `move`
intent, 205 tokens, $0.0002). The model can follow the schema; in-session
output is intermittent — empty/unparseable 200s plus schema-invalid
ramblings. Engine requests are well-formed (`json_mode=True`, bounded
retry with backoff, one repair, then safe WAIT fallback); temperature is
unset (model default). Test story archived.

## Fourth run: pinned temperature 0.2 + player intents (same day)

Created a provider connection and pinned profile revision through the
designed Settings API (`temperature=0.2`, `max_tokens=1024`, deepseek
model), and pinned it on new stories via the draft `ai` section. Schema
adherence improved immediately: character decisions 6/9 succeeded (was
3/9), director 2/2 with compact valid JSON (was 4k-token prose). But all
committed intents were still WAIT — at low temperature the model hews to
"when in doubt, wait", and a validated-but-bland direction ("Ash greets
Wren at the Market.", status `completed`) produced no visible action
across two further beats.

Forced the issue with a player story (Wren controlled): `communicate`
intents accepted two beats running. The pipeline engaged end to end —
reaction (1,866 tokens), resolver (512), director — but the narrator
failed 0/2 and only attempt-echoes were recorded.

## Root cause: narrator token cap starves reasoning models

Direct probe with the real `narrator.v1.md` template:

| max_tokens | finish | reasoning | content |
|------------|--------|-----------|---------|
| 512 (engine default) | length | 491 | 6 chars (`[ {`) — unparseable |
| 2048 | stop | 282 | 417 chars, valid fact-cited beat JSON |

The engine hard-codes `max_tokens=512` in every role graph's deps
(`NarratorGraphDeps`, `CharacterGraphDeps`, `DirectorGraphDeps`), and
`stage1.py` passes only temperature/top_p/top_k from sampling — the
pinned revision's `max_tokens` is never consumed. ~490 reasoning tokens
eat the 512 budget before content starts, so narrator output arrives
truncated-to-empty and records `malformed`. The 2048-cap sample is the
first genuine live prose of the day (narrator voice, fact keys cited).
Voice distinctness for Wren/Ash remains unproven — no dialogue was ever
rendered. Both test worlds archived.

## Fifth run: cap wired through + 4096 pin (same day)

Per maintainer direction, wired `sampling.max_tokens` into all seven
role-graph construction sites in
`backend/.../orchestration/stage1.py` (7-line diff; unpinned default
stays 512, so default behavior is unchanged). Deliberate engine
deviation in vendored code — candidate for upstreaming. Rebuilt the api
image (the image bakes in `backend/src`, recreate alone is not enough),
`ruff` clean, `test_revamp_a05.py` green. Pinned revision 3
(`temperature=0.2`, `max_tokens=4096`).

Decision quality transformed: character completions are now crisp valid
JSON (24–54 tokens), director compact. But every model-chosen intent is
still WAIT, and a `completed` direction produced no visible action.

Player-intent runs (Wren controlled, pinned rev3) engaged the full
pipeline: reaction (1,866 tokens), resolver (up to 7,293 — the 4096 cap
flowing), director. Yet the narrator failed 0/3 (9–13s `malformed`,
not timeouts) while neighboring roles intermittently succeed — something
narrator-specific (largest prompts?) still returns empty 200s on this
model. Only attempt-echoes recorded; both worlds archived.

## Response diagnostics (added this session)

Opt-in provider-boundary diagnostics, off by default, no credentials:
- `ModelGatewayError.detail`: HTTP status, response id, model, finish
  reason, usage (prompt/completion/reasoning), choices count,
  content type/length, provider error/refusal fields. Preserved on
  parse failure into `model_call.result`.
- `CompletionResult`: reasoning tokens, finish reason, response id,
  per-attempt records (retry attempts no longer invisible).
- `model_call.request`: transmitted cap + sampling
  (model/temperature/top_p/top_k) alongside the prompt hash.
- `WORLDSIM_MODEL_DIAG_BODY=1` enables bounded (4KB) raw-body capture
  on parse failure, local DB only.
- Tests: `backend/tests/test_model_diag.py` (6 tests: shape recording,
  envelope, retry attempts, end-to-end persistence).

## Corrections to earlier claims in this file

- The "7.3k tokens proves the 4096 cap" claim was wrong. The transmitted
  cap on those rows was 512; 7,293 was provider-reported usage with
  reasoning tokens counted, not 7k characters of content.
- The temperature-0.2 pin never applied before the art fix below: all
  prior runs used environment defaults, so attributed improvements
  (schema adherence, passivity) were model variance, not pin effects.
- All-WAIT remains an observation; temperature causality was never
  established and is retracted as an explanation.

## Blocking defect found and fixed: snapshot/pin key mismatch

Story creation snapshots `DraftAi` under setup key `"art"`
(`stories/create.py`), but profile resolution read `"ai"`
(`settings/resolution.py`) — which never exists. No created story
could ever use a pinned profile; all silently ran defaults. The
existing test passed only because it hand-wrote the `"ai"` shape,
bypassing creation. Fix: resolution reads `"art"` (one word + comment).
Regression test added (created-snapshot shape); old test aligned to it.
`ruff` clean; `test_revamp_a05.py` + `test_model_diag.py` green.

## Narrator failure anatomy (from recorded diagnostics)

Failing narrator rows: HTTP 200, 1 choice, `finish_reason=length`,
`reasoning_tokens == max_tokens`, content null (type `NoneType` vs
`""` now distinguished). The repair prompt is small (545 chars) — the
model spends the whole budget reasoning and returns nothing. Exact
failing input was extracted from the audit chain and replayed
unchanged against two models:
- deepseek-v4-flash-0731: `length`, ~4,076 reasoning, zero content —
  reproduces the in-session failure exactly on this input and budget.
  This establishes failure on this input, not a general incapability
  of the model.
- gpt-4o-mini: `stop`, 0 reasoning, 258 tokens, valid 4-beat array.

## Fact-key validation defect (found via the trace above)

The b4b8a825 adapter-success text never persisted because graph
validation denied it: `unsupported facts cited:
['attempt:wait: Ash waits']`. The context renders facts as
`- attempt:wait: Ash waits`, so the model glued key+value while the
validator wants the bare key. Fixed at the source: facts now render
as `- key "attempt:wait": Ash waits`, plus one prompt line ("cite
keys exactly as quoted"). Fence tolerance (`unfence_json`) was also
added at the single validate_json choke point. Both covered by tests
proven to fail without their fix. The c5cc9969 milestone beats cite
bare keys and validate with zero repairs — the live proof.

## Completed-direction inspection

Influence directions complete as hook proposals, not immediate beats:
the táo-cake direction persisted narrative_hook "Market Greeting"
(status proposed) with both participant ids; the invented item
("táo cake") is what earned `needs_clarification` on the other world,
while the clean greeting completed. A `completed` queue item plus its
hook row is the effect proof; user-visible action arrives when beats
play the hook, not at completion time.

## Milestone: first persisted rendered interaction (corrected)

Correction: the earlier b4b8a825 claim was wrong. That world ran
UNPINNED (env profile `openrouter/chat-v1`, deepseek model, default
temp, cap 512); its adapter-success narrator text never validated (see
fact-key defect below) and only fallback echoes persisted. The genuine
milestone is world `c5cc9969`, pinned rev8 (deepseek-v4-flash-0731,
temp 0.2, cap 4096 — all recorded per row), beat 2: four persisted
`narration` rows, e.g. `Wren says to Ash: "Ask Ash whether the stalls
are open yet."` (cited `attempt:communicate`) and `Ash waits.` (cited
`attempt:wait`). Reload re-read index 2, phase morning; timeline
consistent with attempts/intents/map; archived normally (200).

"Rendered" means API-returned and DB-persisted narration rows, not
browser-visible play (no browser pass was run on this world). Voice
distinctness is thin (sparse exchange); continuity (Market question →
stalls follow-up across beats 1–2) and state agreement hold.

## Wedged-world recovery (timeout → reopen → reconcile)

World `e5e5ae47` (abandoned 180s client timeout): server showed no
running work (no `started` calls, no leased tasks), one `pending`
execution task, runs idx1 `scenes_assembled` + idx2 `created`.
Reconcile first 500'd on multiple open runs, then 200'd with zero
requeues once idx1 sealed; committed effects intact (index 1,
timeline 3). Retrying the identical beat-2 advance committed cleanly
(timeline 3→5, no duplicates — derived ids make replay idempotent),
then archived 200. An abandoned client request recovers through the
normal guard/reconcile path; nothing was bypassed. Tracked separately
from closed recovery work, as instructed.

### Recovery sequence clarified (code review, not a rerun)

- **What sealed idx1: the original work finished.** The only writer of
  the `scenes_assembled → completed` transition on this path is
  `_finalize` (`backend/src/worldsim/application/orchestration/service.py:576`),
  which seals the run and finishes its task in one transaction at the
  end of the advance coroutine. `reconcile_world` never seals runs —
  it only requeues expired/claimed tasks and reports the open run
  (`service.py:617`), and it reported zero requeues here. No operator
  operation sealed idx1: the abandoned client request completed
  server-side after the client gave up waiting (mid-flight observation
  caught it between the scenes commit and the final seal commit). The
  retry 409s were the open-run guard working as designed.
- **The 500 was self-inflicted.** The second open run (idx2 `created`)
  came from the investigation's own timeout-reopen retry while idx1 was
  still open. With two open runs, `find_open_run`
  (`infrastructure/repositories/phases.py:60`) raises
  `INVARIANT_VIOLATED`, surfacing as 500 instead of a 409. It resolved
  itself once idx1's original work sealed. Minor finding: a multi-open
  state returns 500 where a 409 would be friendlier; recorded
  separately, not fixed here.
- **The normal client can reach the same recovery.** Every recovery
  step was a public API call — advance (409 guard), `POST
  /operations/reconcile` (200 with `open_run_id`/`open_state`; no
  elevated role guard on the route), retry advance (200). Database
  access during diagnosis was read-only `SELECT`s; no state was written
  outside the API.
- **Scope limit.** This demonstrates recovery for one case (late
  server-side completion + idempotent retry via derived ids). It does
  not establish general crash-replay safety. Broader stall recovery
  stays a separate finding.

## Findings (separate)

1. **Provider execution: serving, now observable.** Pins apply
   (recorded per row), decisions validate, narrator renders when the
   model returns content. Remaining narrator empties are precisely
   characterized (finish=length, reasoning==cap) and reproduced in a
   controlled comparison. No fake fallback masqueraded as live output —
   failures are honestly recorded.
2. **Storytelling quality: first persisted beats, depth open.** One
   beat (world `c5cc9969`, pinned rev8) persisted four model-rendered
   rows with dialogue, bare-key citations, and zero repairs; continuity
   across the exchange (Market question → stalls follow-up) and
   state-agreement hold. Adapter-level successes elsewhere did not all
   persist (validation or starvation downstream). Voice distinctness is
   thin; several coherent beats remain future work.
3. **State consistency: holds.** Travel, beats, direction queue with
   hook persistence, player intents, and reload/resume all behaved on
   the live profile.

Integration defects fixed this session (all in vendored code, all
candidates for upstreaming): (1) `sampling.max_tokens` consumed at all
seven graph construction sites (unpinned default still 512);
(2) snapshot/pin key mismatch (`art` vs `ai`) — no created story could
pin a profile; (3) fence-tolerant narrator parsing; (4) unambiguous
fact-key rendering. Plus opt-in provider diagnostics. Profile pinning
via the Settings API is proven working end to end and worth keeping.
