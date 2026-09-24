# Live pinned session — 2026-09-24 (UTC)

## Claim

Current-source API + browser UI, story pinned to a real provider profile.
Every executed model call ran under the requested pin (audit below).
Beats 1–6 (story A, temp 0.2) and 1–4 (story B, temp 1.0) committed through
the UI; reload/continue verified with no duplicate events. Persisted
narration is WAIT-echo prose: the live model genuinely elected WAIT at both
temperatures, so sustained NPC dialogue remains unproven. The milestone
stays at one persisted narration beat.

## Provenance

- Source: `eded8f0` (admission/preflight cleanup committed on top).
- API: working-tree source served on `127.0.0.1:18101` against scratch
  database `embervale_live1` (migrated to head `0038`, seeded stage0-v1).
  Scratch database dropped after the session; user compose stack untouched.
- UI: `vite dev --port 5174` proxied to `:18101` (temporary
  `vite.config.ts` edit, restored afterwards).
- Pin: openrouter connection `3927e5e8-…`, profile
  `284533dd-…` revision 2 (`deepseek/deepseek-chat`, temperature 0.2) for
  story A; revision 3 (temperature 1.0) for story B. Key read from the local
  `.env` at runtime, never written to evidence.
- Stories (both archived after the session):
  `a49aa6d8-…` (index 6), `c27f4ba0-…` (index 4).

## Method notes (honest scaffolding)

- The wizard has no model-pin picker, and Begin always re-saves UI
  selections (dropping any out-of-band pin). The pin was merged into the
  wizard's own save request via test-harness request mediation, so every
  click (wizard, review, Begin, beats, seats, directions) happened in the
  browser. Product gap: in-UI pinning is impossible today.
- Direction interpretation runs on the environment gateway, not the story
  pin, and its calls are not recorded as `model_call` rows. One filing
  received a rich live clarification (screenshot); later filings hit the
  generic mapping fallback (free-pool flakiness, as in prior sessions).
- `needs_clarification` items disappear from the queue on reload
  (list shows queued only); resubmit works only in the filing session.
- Player attempts need a bound player seat; the story grant overrides role
  headers (seat must be taken first).

## Results

- Beats executed under `openrouter / pin-284533dd-r2` (story A) and
  `pin-6e790d13-r3` (story B): 32/32 calls `succeeded`, zero errors, zero
  environment rows. See `audit.json`.
- Narration rows match the visible feed exactly (WAIT echoes, distinct
  voices per character). No live dialogue prose was generated.
- Live generated content observed: one contextual clarification
  (location mismatch Hearth/Market with options, `shots/16-…`), plus
  schema-valid WAIT decisions at both temperatures.
- Reload: feed 10 entries matched persisted state; beat 4 added exactly 3
  (2 actions + tick), no duplicates. Replay of beat 4 returned duplicate.
- No page errors across the session.
