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

## Future runs

`results.json` now records the actual tested tree at run start:

- `commit` — `git rev-parse --short HEAD`.
- `dirty` — whether `git status --porcelain` reported anything.
- `diffSha256` — sha256 of `git diff HEAD` (tracked modifications).
- `untracked` — untracked paths present at run start.
- `only` — the `--only` subset filter, if any (partial runs are marked).

A run with `dirty: true` or a non-empty `only` is not whole-tree evidence.
Prefer committed trees for record runs.
