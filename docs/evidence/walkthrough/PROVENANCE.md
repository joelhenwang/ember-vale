# Walkthrough evidence provenance

## 2026-09-22 run (`results.json` at `2026-09-22T17:01:10Z`)

The recorded `commit` field says `4a56c86`. That run did **not** test the
clean `4a56c86` tree. It tested `4a56c86` **plus uncommitted working-tree
modifications**:

- `scripts/walkthrough.mjs` — the four new studio scenarios
  (`adoptretry`, `publishretry`, `finishblocked`, `duplicateroute`), the
  `--only` subset gate, the `Idempotency-Key` header support in `apiCall`,
  and the throwaway-preset / field-control helpers.
- `src/composables/useEditorDraft.ts` — retire-and-reopen recovery for a
  draft left open on a superseded base (reload after publish).
- `src/composables/useEditorDraft.spec.ts` — the recovery regression tests.

The round-trip product changes under test (`src/game/studio.ts`,
`src/game/studioFields.ts`, `WorldStudioView.vue`) were clean in `4a56c86`.
All of the above working-tree changes were committed in `9a7b4fb`
(plus evidence), except whitespace-only `prettier --write` normalization
applied to the spec and the walkthrough after the run.

Read that `results.json` as **baseline `4a56c86` plus the listed
modifications**, not as verification of the clean baseline commit.

## Runs after 2026-09-22

These carry inline tree identity (`commit`, `dirty`, `diffSha256`,
`untracked`, `only`) in `results.json` itself; the note above applies
only to the 2026-09-22 record.

## 2026-09-22 subset (`results-firstcreate-twostories-2026-09-22.json`)

18/18 PASS, `only: [firstcreate, twostories]`, at `2026-09-22T23:45:41Z`.
The recorded `commit` is `0d63193` with `dirty: true`: the tested tree
was `0d63193` plus working-tree modifications comprising the 7 files
committed as `b5c56ee` (creation replay/superseded controller, both
studio handoffs, the ambiguous-creation and two-story scenario
extensions, and the ledger note). Read it as verification of that
code — the first-preset ambiguous-creation replay and the full two-story
independence proof — not as whole-tree evidence.

## 2026-09-23 subset (`results-firstcreate-2026-09-23.json`)

15/15 PASS, `only: [firstcreate]`, at `2026-09-23T00:30:00Z`. The
recorded `commit` is `b5c56ee` with `dirty: true`: the tested tree was
`b5c56ee` plus the uncommitted dismiss-bypass correction (dismiss hides
the notice only; the recovered association and set-aside edits survive
dismissal and reload), the wizard-origin creation handoff (return
adoption offer, character-add and cast-full plans, entry links), and
the matching scenario extensions. Read it as verification of that
code — dismiss-plus-reload leaving one preset with ordinary Create
withheld, and the world/character creation adoption proof — not as
whole-tree evidence.

## 2026-09-23 subset (`results-addrollback-2026-09-23.json`)

10/10 PASS, `only: [addrollback]`, at `2026-09-23T01:07:16Z`. The
recorded `commit` is `c324807` with `dirty: true`: the tested tree was
`c324807` plus the uncommitted character-add rollback correction
(controlled key in adoption snapshots, restored on dismiss, compared
for intervening edits) and the matching `addrollback` scenario.
Read it as verification of that code — failed character-add accept
controlling the newcomer locally, dismiss retry removing it and
restoring no-control, persistence recovery, reload, and the preserved
intervening location with an untouched server — not as whole-tree
evidence. The reload passes through the designed recovery choice
("server version chosen") because a stale failure snapshot never
compares covered; see the ledger findings.

## Future runs

`results.json` now records the actual tested tree at run start:

- `commit` — `git rev-parse --short HEAD`.
- `dirty` — whether `git status --porcelain` reported anything.
- `diffSha256` — sha256 of `git diff HEAD` (tracked modifications).
- `untracked` — untracked paths present at run start.
- `only` — the `--only` subset filter, if any (partial runs are marked).

A run with `dirty: true` or a non-empty `only` is not whole-tree evidence.
Prefer committed trees for record runs.
