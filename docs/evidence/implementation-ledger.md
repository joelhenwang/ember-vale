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
| E3 Library/studios | Preset CRUD/revisions/archive/duplicate/import-export + durable editor drafts with strict-merge publish, durable publication receipts, completed-draft lifecycle (backend, migrations 0035/0036); wizard reads server presets pinned; Library worlds/characters from server presets with unknown-usage/rev metadata, no recency sort, preview-labeled mocks; studios use route-based identity with loading/failed/missing states | Draft lifecycle + barrier suites (14), backend neighbors green, 131/131 frontend, typecheck/lint/prettier/basedpyright clean (2026-09-21) | REMAINING — editor UI wiring (useEditorDraft + studio save/publish states); nested return flow with deliberate adoption; E3 proof incl. server-only preset, failed saves, ambiguous publish retries |

E3 lifecycle decisions (2026-09-21): new presets stay local (studio.ts drafts) until Publish sends one complete validated `create_preset` — no placeholder rev 1. After publication the receipt survives completion, so identical retries replay; `complete` retires only the receipt-matching version (newer edits need explicit discard); `discard` voids the receipt. Publish renames update the preset display name atomically; revision payloads stay immutable.

E3 publication corrections (2026-09-22, uncommitted): receipts are per draft/version (migration 0037, PK `(draft_id, draft_version)`), so publish → edit → save → publish lands a new revision under its own receipt and every earlier publication still replays. Replay resolves the requested draft's receipt even while a successor draft occupies the preset, without touching it. `POST .../publish` returns `PresetPublishView{published_revision, detail}` so replay names the exact revision apart from the Library head (contract regenerated: `content/schemas/openapi.json`, `content/clients/worldsim.ts`, `PresetPublishView` added to the generator's model list). Corrected the "versions advance only when fields change" claim: every successful save advances the version, so a matching version implies matching fields. Verified: 17/17 draft service + HTTP replay tests, 29/29 with library neighbors, ruff clean on touched files, frontend 131/131 + typecheck + lint clean. Pre-existing failures unrelated to this change (identical on clean `c89e1e1` tree): `test_domain_schema` committed-bundle drift, 3× `test_revamp_p09` + 1× `test_revamp_p08` activity-completion stalls, plus ruff/basedpyright noise in untouched files. REMAINING — `useEditorDraft` + studio save/publish states (reload-persistent local drafts, safe ambiguous-first-create handling still required); nested return with explicit revision adoption; E3 journey proof.
| E4 Settings/live text | Settings shell, provider/model selects; connection tests are DEMO fakes | Never live-verified | Live provider/credential verification; no fake reachable badge |
| E5 Player/Observer | PlayView: grant/actor identity, travel, beat advance, seats, interventions queue | Deterministic suites green | Full observatory (map-led, event modal, autoplay, perspective filters); `/adventure` + `/world` routes unwired |
| E6 Director/God | Seats, interpretation, queue, execution via beats, per-step identities | 69/69 backend 2026-09-21; 126/126 frontend | Live-provider execution; browser direction execution |
| E7 Artwork | Placeholder registry + `setGeneratedImage` seam | Registry fallback/override specs | Asset service/jobs, profile→body lineage, event modal art |
| E8 Living characters | Static sheets | — | Inventory, physique/injuries, relations/memory |
| E9 Saves/operations | Archive/unarchive, setup provenance | Suite-covered | Checkpoints/branches, backup/restore proof |
| E10 Long-term sim | Phase clock, conditions tick/expiry | Condition suites | Macro compression, eras, lineage |
| E11 Release hardening | — | — | Visual/a11y/deployment matrix, honest feature matrix |
