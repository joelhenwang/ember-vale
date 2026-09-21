# Implementation ledger — Ember Vale product packets

Closed E6 correction (through commit `919303b`, reviewed 2026-09-21):
E6-A authoritative identities, E6-B actor reservation, E6-C durable
per-step effect identity (migration 0034), E6-D receipt reconciliation.
Recovery and creation-departure closures preserved. Per-step
evidence in `docs/evidence/e6-execution.md`; session handoff in
`docs/reviews/Ember_Vale_Fresh_Session_Handoff.md`.

Outstanding reliability requirement (tracked separately, NOT part of
E6 closure): partial-scene crash recovery between scene commits.
Effect-level interruption/concurrency is proven; whole-beat re-commit
idempotency is pre-existing beat behavior and remains unproven.
Do not claim lossless/exactly-once execution until it is covered.

Journey/browser verification runs when the required environment and
permissions are available; current evidence is inherited until then.

| Packet | Implemented | Verified | Blocked / remaining |
|---|---|---|---|
| E0 Baseline | UI baseline, reference backend pinned | Screenshots recorded (inherited) | — |
| E1 Backend spine | Coherent FastAPI/Postgres engine, isolated compose DB, Vite proxy, generated contract | Health live/ready, restart-safe (inherited + journey) | — |
| E2 First journey | Starter presets rev 2, server story drafts, atomic idempotent create, PlayView travel + beat advance | Deterministic journey create/resume (inherited); travel/replay suites green 2026-09-21 | Browser journey re-verification pending env |
| E3 Library/studios | Preset CRUD/revisions/archive/duplicate/import-export (backend); wizard reads server presets with pinned revisions; Library worlds/characters tabs read server presets with loading/error/empty states, studios resolve names server-first (slice 1) | Mapper + filter specs, 131/131 frontend, typecheck/lint/prettier clean (2026-09-21) | REMAINING — packs/templates still mock; durable editor drafts + publish; nested return flow; E3 proof (edit rev 2, reload, select, independent story) |
| E4 Settings/live text | Settings shell, provider/model selects; connection tests are DEMO fakes | Never live-verified | Live provider/credential verification; no fake reachable badge |
| E5 Player/Observer | PlayView: grant/actor identity, travel, beat advance, seats, interventions queue | Deterministic suites green | Full observatory (map-led, event modal, autoplay, perspective filters); `/adventure` + `/world` routes unwired |
| E6 Director/God | Seats, interpretation, queue, execution via beats, per-step identities | 69/69 backend 2026-09-21; 126/126 frontend | Live-provider execution; browser direction execution |
| E7 Artwork | Placeholder registry + `setGeneratedImage` seam | Registry fallback/override specs | Asset service/jobs, profile→body lineage, event modal art |
| E8 Living characters | Static sheets | — | Inventory, physique/injuries, relations/memory |
| E9 Saves/operations | Archive/unarchive, setup provenance | Suite-covered | Checkpoints/branches, backup/restore proof |
| E10 Long-term sim | Phase clock, conditions tick/expiry | Condition suites | Macro compression, eras, lineage |
| E11 Release hardening | — | — | Visual/a11y/deployment matrix, honest feature matrix |
