# perf-llm-001: LLM cost, latency and caching from the stored traces (free)

**Question.** Where do the model calls spend money and time, does any role's prompt grow
without bound, and are there wasted calls (truncations, repairs, hedge twins)?

**Setup.** This is a read-only analysis of the dev database on 2026-10-08:
- 3,947 `model_call` rows from 2026-09-20 to 2026-10-08, across 137 worlds;
- `model_cost`, `phase_run`, `image_job` and `asset_record`.

The script is `backend/scripts/llm_usage_report.py --current`, which keeps only the prompt
versions in use now (character_decision.v7, reaction.v4, resolver.v4, narrator.v4,
director.v12, summary.v1, digest.v1). The full output is in `report-current.json`. No paid
calls were made.

## Findings

### 1. Where the money goes (current prompts)

| role | model | calls | prompt avg | prompt p95 | completion avg | cached | latency p50 / p95 |
|---|---|---|---|---|---|---|---|
| reaction | deepseek-v4-flash | 560 | 5,324 | 6,684 | 141 | 66% | 1.9 / 6.4 s |
| character_decision | deepseek-v4-flash | 362 | 5,198 | 6,951 | 107 | 56% | 1.6 / 4.2 s |
| character_decision | venice-uncensored-1-2 | 168 | 5,336 | 6,986 | 124 | 59% | 1.8 / 2.5 s |
| reaction | venice-uncensored-1-2 | 106 | 5,577 | 7,092 | 138 | 63% | 1.8 / 2.7 s |
| resolver | deepseek-v4-flash | 130 | 3,426 | 3,592 | 290 | 65% | 2.6 / 5.2 s |
| daily_summary | deepseek-v4-flash | 59 | 1,549 | 2,025 | 780 | — | 7.1 / 30.7 s |
| narrator | venice-uncensored-1-2 | 56 | 2,058 | 2,430 | 211 | 52% | 2.1 / 5.3 s |

Reactions and decisions make up ~80% of tokens. Their prompts are ~5–7k tokens, with output
around 110–140 tokens, so the cost is almost all input. That makes cache hits the main
lever, and they are already 56–69%.

Splitting each beat's first call from the later ones shows the first is already 50–59%
cached (warm from the previous beat). Running the first call alone to warm the cache would
gain ≤1–2 points (character on DeepSeek: 55.8% → 56.9%) at +1.6 s per turn. **Not
worth it.**

### 2. Prompts are bounded (good)

Prompt tokens per call by story length, in 10-beat buckets:

| role | beats 0–9 | 10–19 | 20–29 | 30–39 | 40+ |
|---|---|---|---|---|---|
| character_decision | 4,639 | 6,113 | 6,658 | 6,772 | 6,618 |
| reaction | 4,731 | 5,770 | 6,470 | 6,563 | 6,528 |
| resolver | 3,422 | 3,470 | 3,489 | 3,461 | 3,373 |
| director | 2,050 | 2,486 | 2,286 | 2,316 | 2,332 |

Decisions and reactions grow for about 20 beats, then plateau at ~6.6k tokens (max 7.4k).
The context budgets from 00418d8 hold, so no role grows without bound.

### 3. Cost per beat

There were 294 beats on current prompts: 5.2 calls per beat on average and ~24.6k prompt
tokens per beat. The slowest call in a beat has a median of 2.7 s.

**Correction on spend accounting:** most stored cost rows are *estimates*.
- Billed DeepSeek rows (OpenRouter `usage.cost`, `estimated=false`, 196 rows) work out to an
  effective $0.18 per Mtok in and $1.26 per Mtok out.
- Venice reports no billed amount, so its 422 rows were costed at `DEFAULT_RATE`
  ($1 / $3 per Mtok).
- Venice's own list price (`GET /models`, `model_spec.pricing`) is $0.20 / $0.90 per Mtok,
  so stored Venice spend is ~4.5x too high.
- The `usd` columns in the report therefore overstate anything that is `estimated=true`.

Fix: `domain/costs.py` now prices `venice-uncensored*` and `gemma-4-uncensored` at Venice
list price (`PRICING_VERSION` s3-prov-v3). Old rows keep their recorded version.

### 4. Wasted calls

- **Daily summaries were truncated.** 9 of 71 traced summaries stopped at the 1,024-token
  cap mid-JSON: 8 of 12 on Venice (Venice summaries that finish run ~935 tokens) and 1 on
  DeepSeek. Each was followed by a repair at the same cap. Fix: the `summary` floor in
  `ROLE_MAX_TOKEN_FLOORS` is now 1,536. A cap only limits output, so a summary that fits
  costs the same.
- **Hedge twins are paid but not traced.**
  - Calls slower than their hedge delay, which very likely started a twin:
    - reaction: 11.6% (> 4 s);
    - character: 4.2%;
    - resolver: 1.8%;
    - **daily_summary: 35.7% (> 10 s)**.
  - A cancelled twin is still generated and billed upstream, but only the winner is traced,
    so real spend is somewhat higher than recorded.
  - Summaries run in the background (f6ba34d), off the player's path. Hedging them buys no
    felt latency and costs about a third more summary calls.
  - **Recommendation (P2 / gateway owner):** turn hedging off for `summary` (and `digest`).
    Also trace the twin's usage, or at least count twins per beat.
- **Repeat calls per (beat, actor, role).** 11% of decisions had a second call in the same
  beat (repeat-guard retry or repair). Reactions repeat by design, one per (attempt,
  reactor).

### 5. Images

| | |
|---|---|
| jobs | 115, all `ready`, attempts 0 (no retries recorded) |
| `image_job` timing | none: the table has no created/started/finished timestamps, so queue wait vs paint time **cannot be measured** |
| painted output | WebP, about 1280×720 scenes, 512² portraits |

Storage on disk in the `generated` volume is 113 MB:
- **59 map PNGs hold 112.7 MB (1.9 MB average, up to 4.3 MB)**: uploaded or painted maps are
  stored and served as full-size PNG;
- 41 WebP hold 4.6 MB.

The built-in seed art (`content/assets/revamp`, 9 files, 14 MB) is PNG and is referenced by
every built-in story. Re-encoding it as WebP q86 measured 13,383 KB → 1,800 KB (7.4x), for
example the map master 5.2 MB → 815 KB and the market background 3.2 MB → 519 KB.

**Recommendations (asset route / upload owners):**
- Store map uploads as WebP, ≤2048 px (the `shrink` module exists).
- Serve the seed art as WebP.
- Send `Cache-Control: private, max-age=31536000, immutable` on `/assets/{id}`, which is
  content-addressed by id and today has no caching headers.
- Add `created_at`, `started_at` and `finished_at` to `image_job` so the image pipeline can be
  measured.

## Verdict

- **Adopted** (tests green):
  - Venice list prices in the cost table;
  - summary floor 1,536.
- **Not adopted, measured:** serial warm-up for caching (≤2 points, +1.6 s).
- **Needs a paid run to confirm (not run):**
  - The summary floor change on Venice. One playtest of ~30 turns to the first day-end is
    ~$0.05 on DeepSeek (billed rate) or ~$0.04 on Venice.
  - Hedge-off for summaries needs no quality run; cost only goes down.
