# Beat latency 001 — live beats on deepseek/deepseek-v4-flash-0731

Fresh watcher story per run (Wren and Ash both at the Hearth), 3 beats each,
via `scripts/beat-latency.mjs`. Per-stage wall time from
`X-Worldsim-Phase-Timings`; per-call data from `/stage1/model-runs`; spend
estimated from OpenRouter public prices. Total spend for all four runs plus
four single-call reasoning probes: about $0.03.

| Run | Code | Reasoning | Beat wall time | Calls/beat | Outcome |
| --- | --- | --- | --- | --- | --- |
| `baseline-reasoning-default` | 2391f8e | model default | 27 s, 58 s, 71 s | 3 | 8/9 calls spent the whole token cap thinking (`finish=length`, malformed); every beat fell back to wait/no-op |
| `reasoning-off` | 2391f8e | `off` | 9.5 s, 7.1 s, 6.6 s | 3–5 | all calls valid, but characters only ever wait/observe |
| `reasoning-off-context` | 527d720 | `off` | 37 s, 47 s, 56 s | 7–9 | characters converse, react in quoted speech, resolver records memories, narrator writes the scene |
| `reasoning-low-context` | 0778097 | `low` | 74 s, 107 s, 91 s | 6–7 | 6/20 calls exhausted the cap thinking (up to ~1,000 reasoning tokens); fallbacks in resolver, reaction, director, narrator |

## Findings

1. **Hidden reasoning broke the live world.** With the model default, DeepSeek V4
   thinks before every answer and runs out of tokens (512 for decisions, 768
   for the director) before writing JSON. All outputs fell back. Fixed by
   `WORLDSIM_PROVIDER__REASONING=off` (2391f8e); not yet the default in `.env`.
2. **Characters could not act on anything.** The decision context never named
   who else was present, listed routes as bare ids, and never gave the actor's
   own ids. Only wait/observe were formable. Fixed in 527d720.
3. **Remaining time is provider throughput plus repairs.** No reasoning tokens
   remain, but output speed varies 10–120 tokens/s between identical-sized
   calls, so a 110-token decision takes 1.7–11 s. The stage chain is serial
   (decide → react → resolve → narrate), so slow calls add up.
4. **Repairs cost a full serial round trip (2–15 s) each.** Causes seen:
   - decision: a `wait` that also listed every other family's fields as `null`
     (10 schema errors);
   - director: an extra `"type": "json_object"` key;
   - resolver: `expected_versions` must cover every affected id, a value the
     model cannot know.
   All three are deterministic to normalise server-side.
5. **`low` is not low on this model.** Effort `low` still spent 60–1,077
   reasoning tokens per call: beats doubled in time, spend doubled, and 6 of
   20 calls fell back. Raising caps would trade the fallbacks for more
   latency. On DeepSeek V4 Flash, `off` is the only usable level; revisit
   per role if a model with a controllable thinking budget is adopted.
