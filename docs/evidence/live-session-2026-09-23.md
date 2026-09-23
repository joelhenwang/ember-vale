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

## Findings (separate)

1. **Provider execution: attempted, not achieved.** Configuration is correct
   and requests reach OpenRouter, but 0/20 generations succeeded. No fake
   fallback masqueraded as live output — failures are honestly recorded.
2. **Storytelling quality: unproven.** No live prose was produced, so voice
   distinctness, continuity, and travel/state agreement in narration cannot
   be judged from this session.
3. **State consistency: holds.** Travel, beats, direction queue, and
   reload/resume all behaved on the live profile.

No blocking integration defect was fixed: the engine records `rate_limited`
and falls back without retry, and that orchestration lives in the vendored
read-only engine. Two independent provider pools (Google, Qwen) throttled
within the same hour, so further free-model rotation has diminishing
returns. Remedies for the maintainer: retry when the free pool clears, use
a credited key or non-free model (real cost — maintainer decision), or
revisit retry semantics in the engine (out of scope for this task).
