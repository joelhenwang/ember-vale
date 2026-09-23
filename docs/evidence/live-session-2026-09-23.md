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

## Findings (separate)

1. **Provider execution: serving, but unreliable.** Configuration is
   correct, requests are billed, and 5/12 deepseek calls succeeded at the
   adapter. But intermittent empty/unparseable responses plus
   schema-invalid output under `json_object` mode mean no beat ever
   produced narratable actions (free-tier pools: 0/30 across two models).
   No fake fallback masqueraded as live output — failures are honestly
   recorded.
2. **Storytelling quality: unproven.** No live prose was produced, so voice
   distinctness, continuity, and travel/state agreement in narration cannot
   be judged from this session.
3. **State consistency: holds.** Travel, beats, direction queue, and
   reload/resume all behaved on the live profile.

No blocking integration defect was fixed: the engine records `rate_limited`
and falls back without retry, and that orchestration lives in the vendored
read-only engine. Paid flash serving works but is too flaky at default
sampling for strict-schema roles. Remedies for the maintainer: pin a
more capable model, pin a low temperature via profile revision
(currently unset), retry free pools when they clear, or revisit
graph/adapter robustness in the engine (out of scope for this task).
