# Backend test tiers

Run from the repository root with `uv run --project backend`.

| Tier    | Command                                            | Contents                                             |
| ------- | -------------------------------------------------- | ---------------------------------------------------- |
| Routine | `python -m pytest backend/tests`                   | Unit, contract, and DB/API tests; excludes long sims |
| Gates   | `python -m pytest backend/tests -m "not soak"`     | Routine plus `sim_gate` multi-phase simulation gates |
| Soak    | `python -m pytest backend/tests -m soak`           | Diagnostic 300-phase soak only                       |
| Live    | `WORLDSIM_LIVE_SCENARIO=1 python -m pytest backend/tests/test_s3_live.py` | Keyed provider sample; skipped otherwise |

`sim_gate` (70/300-phase gates, quality baselines, two-year succession) runs
before merging a slice and on orchestration/memory changes. `soak` runs for
explicit performance investigations or scheduled checks.

Database isolation: one migrated template per invocation, cloned per test;
scratch names are unique per worker and run. `WORLDSIM_EVIDENCE_DIR`
relocates regenerated evidence bundles; `WORLDSIM_QUALITY_BASELINE`
relocates the quality baseline file.
