# Recovery storage-boundary evidence provenance

## 2026-09-25 run (`results-2026-09-25.json`)

Tested tree: `12aee70` plus the uncommitted recovery storage-boundary
changes (filing identity, first-wins primary with separately kept
contenders, refused marking, durability reporting, strict intent shape
validation, invalid-vs-absent reads) in:

- `src/composables/pendingSubmissions.ts`
- `src/composables/pendingSubmissions.spec.ts`
- `src/composables/useStory.ts`
- `src/composables/useStory.spec.ts`
- `src/views/PlayView.vue`

The recorded `diffSha256` covers exactly those five files. No production
code drift: backend files are untouched, token budgets unchanged, no
model spend (deterministic fetch mocks only).

## What the record asserts

The results file carries source identity (commit, dirty flag, diff hash)
and request/outcome assertions for the two storage boundaries:

1. Two controllers sharing one store: Q1 filed first (primary), Q2 filed
   second (contender), Q2 refused with 409, Q1 interrupted, reload,
   resume replays exactly Q1 at the stranded index, Q2 retained
   separately and surviving Q1's commit.
2. Throwing `setItem`: the filing is flagged session-only, the 409
   notice says so, a fresh controller finds the slot absent (not
   corrupt), and its resume replays bare with no `player_intents`.
3. Corrupt bytes read back as invalid (reported in the room), distinct
   from an absent record (silent).
4. Strict replay gating: arrays, empty maps, unknown families, and
   entries without actor/snapshot identity never replay.

## 2026-09-25 correction (`results-2026-09-25-correction.json`)

Follow-up review showed the prior design's atomicity claim was wrong:
synchronous execution does not make a localStorage read-modify-write
atomic across tabs, and the shared primary slot permitted an
overlapping-claim sequence that destroyed the original. The slot is
removed. Each filing writes only its own unique key (no shared mutable
state, so overlapping claims coexist by construction); ownership is
elected at read time (earliest unrefused, well-formed filing for the
stranded index); refusal and retirement touch only the filing's own key
(idempotent). The same correction makes durability explicit:
`defaultSubmissionStorage()` probes writability and flags an
inaccessible-localStorage fallback as session-only, and thrown reads
report `unavailable` instead of `absent`.

## What this record does not claim

- The earlier live-Edge browser walkthrough left no preserved
  driver log, results file, or screenshots; it is not independently
  inspectable from this record. The controller-level regression above
  now carries the same request/outcome assertions durably.
- The backend timeout-recovery tests were not rerunnable here: the
  project venv has no local Postgres to connect to
  (`localhost:5432` connection timeout, no service or binaries
  present). Backend files are untouched by this slice, so the earlier
  controlled-clock busy-expiry coverage stands unmodified, not
  re-verified.
