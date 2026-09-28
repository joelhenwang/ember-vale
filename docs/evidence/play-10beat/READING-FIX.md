# Reading-view fixes: verification (no new paid session)

Two defects found in review of the 10-beat run, both fixed and verified
with deterministic fixtures plus browser checks against this story's own
stored records. No new gameplay session was run; the original
`results.json` (including its failed `reload keeps structured beat cards`
check) is preserved unmodified below.

## Defect 1: unquoted topics presented as dialogue

`sceneLines()` turned every `communicate` intent/reaction into a
speaker-labelled line. `Market stalls` is a topic, not words spoken.

Correction (supersedes the first fix, which wrongly gated quoted topics
on scene resolution success): spoken lines come from persisted DIALOGUE
beats only. Scene resolution outcome never proves an individual
utterance committed — the backend commitment check reads the reaction's
own status, which the scene API does not expose.

Fix (`src/components/story/beatReading.ts`, pure, fixture-covered):

- Persisted DIALOGUE beats speak. Nothing else does, regardless of
  quotation or resolution outcome.
- All supplementary topics stay verbatim records in Beat details
  (`Communication records (topics as filed — not speech)`), quoted or
  not. No speech — and no "not committed" — is inferred from the
  outcome. A later need for committed speech must expose its
  authoritative source status explicitly.
- Redacted (perspective-hidden, null) detail renders nothing.

Regressions (`beatReading.spec.ts`, 13 tests): quoted intent plus
scene success manufactures no dialogue; dialogue stays visible with
failure/impossible outcomes; missing narration causes no commitment
claim either way; unquoted topics stay records; redacted silence;
dialogue precedence; stored ordering; attempt-record exclusion;
pointer aggregation order/dedupe; citation order.

In-vivo (existing story `d5104e8a`, seeded real pointers, fresh
profiles): beat 10 renders one Ash dialogue line, no duplication
(`rich-beat10.png`); beat 5 (no dialogue beats, fallback) renders zero
spoken lines, zero flow topics, and the verbatim record in Beat details
(`beat5-summary.png`).

## Defect 2: one-card-per-beat hid additional scenes

`beatReading()` returned the first pointer only. Now
`collectScenePointers()` aggregates every distinct scene pointer in
timeline order; `BeatEntry` renders one segment per pointed event (its
scenes in stored order — dialogue and narration interleaved, never
grouped), legacy snippet lines for entries without pointers, and the
event's own snippet lines for scenes whose reads fail. `loadBeatDetail`
settles each scene independently; the beat counts as failed only when
every scene fails.

Regressions: `beatReading.spec.ts` (two-pointer order, dedupe, empty
skip); `useStory.spec.ts` (two-scene beat loads both in order; a failed
scene keeps its sibling with `failed: true` and null detail; beat failed
only when all scenes fail). No two-scene beat exists in the live stores
(all recorded beats carry one scene), so multi-scene rendering is proven
by these deterministic tests, not by a live beat.

Post-fix natural path: beat 12 committed through the room UI on a fresh
profile (pointers recorded by the commit itself, no seeding) renders
Ash's dialogue plus Beat details (`beat12.png`), with the waiting notice
observed ticking at 8s/33s/58s beforehand.

## This story's own per-beat record (read-only duplicate replays + scene reads)

| beat | kind     | resolution                    | dialogue voiced          | narration prose                   |
| ---- | -------- | ----------------------------- | ------------------------ | --------------------------------- |
| 1    | travel   | committed (no advance report) | n/a                      | none                              |
| 2    | question | success                       | Ash answers              | none (attempt records)            |
| 3    | question | success                       | Ash answers              | none                              |
| 4    | question | impossible                    | Ash answers              | none                              |
| 5    | question | success                       | none — 4 attempt records | none; commit-time fallback notice |
| 6    | travel   | committed (no advance report) | n/a                      | none                              |
| 7–11 | question | success                       | Ash answers              | none                              |
| 12   | question | impossible                    | Ash answers              | none; commit-time fallback notice |

Session-wide, from these records (not inferred from other arms):
model-authored narration prose is absent in all 12 beats; dialogue
answers were delivered on every question beat except beat 5.
