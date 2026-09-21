# Fifth-push corrections — evidence (draft ownership + navigation), 2026-09-21

Follow-up against `docs/reviews/Ember_Vale_Fifth_Push_Review_and_Guide.md`.
Two bounded corrections; no backend changes, no styling changes.

## 1. Creation and queued work owned by their draft (`useStoryDraft.ts`)

- Pending submission receipts live in a module-level map keyed by draft
  ID (persisted to localStorage, validated on load) and survive draft
  switches and wizard reopening. `createWorkflow` replays only the receipt
  belonging to the draft it started with; B's Begin never sends A's
  receipt, and A's receipt is preserved for A's own retry with its exact
  ID/version/key.
- Create errors are stored per draft ID; the displayed error follows the
  mounted draft. Acknowledgment snapshots reset per loaded draft; other
  drafts' receipts, errors, and recovery are untouched by loads.
- Queued saves capture draft identity plus an immutable input snapshot at
  enqueue time. At execution they PATCH that same draft using its next
  acknowledged version (tracked per draft, live-read when current, fetched
  when behind navigation) — never a frozen obsolete version, never B.
  Late completions from A change nothing observable on B and navigate
  nowhere; the view additionally refuses to route into a story when the
  mounted draft changed mid-workflow.
- Controller-level generation guards load completions: a slow A load
  resolving after B took over is dropped.
- Removed the dead unscoped `submit()` path (no callers).

Focused regressions (`useStoryDraft.spec.ts`, 15 tests): ambiguous A →
B Begin sends only B; return to A replays A's original ID/version/key
with zero PATCHes; a fresh controller instance replays the persisted
receipt; queued A saves behind B's navigation PATCH only A and leave B
mounted; slow-A/fast-B load keeps B.

## 2. Edits protected during in-app navigation

- The wizard snapshots the latest selections + step into a per-draft
  recovery slot on route leave and draft-query update (previously only
  failed saves wrote recovery, and only into one global slot). Clean
  navigation stays immediate — nothing blocks the route.
- Boot restores a recovery snapshot only when it validates (shape, role,
  timestamp) and is newer than the server state, labels it explicitly
  local (“kept locally on this device… only a successful save marks it
  saved”), and never presents it as a server save. Successful saves clear
  only the owning draft's slot.
- Receipts and editable snapshots are stored separately: recovery never
  overwrites an unresolved create receipt.
- A storage banner informs when browser storage is unavailable (tab-only
  durability); mounted input is always retained.

## Browser evidence (extended walkthrough, 28/28)

`node scripts/walkthrough.mjs` — headless Edge, dev server + compose
stack; results in `docs/evidence/walkthrough/results.json`:

- **wizardplayer** (new): full wizard Player creation with explicit Wren
  selection → review shows “Player as Wren” → room grants Player with the
  actor locked → reload keeps grant and lock (screenshot kept).
- **dirtynav** (new): unsaved cast survives Home-and-back with local
  labeling; failed save → newer edit → leave → reopen keeps the newest
  edit.
- Kept: Observer create/travel/beat/reload/Home, API-seeded Player
  movement, stopped-API failed-save + retry, all-routes compile gate,
  narrow screenshots.

## Gates

- Frontend: 111/111 vitest (16 files), `vue-tsc` clean, `eslint` clean,
  Prettier clean on touched files.
- Walkthrough re-ran after the final format pass (Prettier reflowed the
  wizard template): 28/28 live checks green.
- Backend: unchanged this pass, so no backend rerun (per the review's
  verification note).

Remaining limitation: narrow screenshots show rendering at 390px but do
not establish 200% zoom accessibility, as before.
