# Visible dialogue — live round 5, 2026-09-24 (UTC)

## Claim

The committed-communication → attributed-narration → visible-dialogue path
works live end to end, including the narrator-outage fallback:

- Q1 beat: 6/7 provider (only the narrator call failed, `reasoning_only`).
  Ash's reaction answered `communicate` with Wren's real ID, validated and
  committed. The narrator outage did **not** lose the answer: the fallback
  persisted `[dialogue] speaker=Ash, cited=[reaction:dc39…], text="Market"`
  through the same feed path, and the room displayed it.
- Q2 follow-up ("say more about the Market: which stalls stand today?"),
  built on that answer, committed with provider 4/5 (Ash's reaction call
  burned `reasoning_only`; Wren's WAIT, model resolver, and model narrator
  succeeded). The model narrator stuck to attempts ("Ash waits") and did
  not hallucinate an answer.
- Totals: 12 calls, 10 succeeded; 3 committed reactions (Ash communicate,
  Wren WAIT ×2); 7 narration rows, one DIALOGUE with Ash's speaker ID.

Answer continuity remains pending: the follow-up drew no new answer, so no
sustained exchange is established. The feed renders beat text but has no
speaker chip — `speaker_id` is persisted and API-visible, but the room
shows the words without naming Ash. That display gap is noted, not fixed
in this slice.

## Provenance

- Source: working tree past `cdc61fb` (38th push) with the narration
  voicing change (`communication_facts` input, per-reaction citation keys,
  speaker-vs-source validation, deterministic DIALOGUE fallback, narrator
  dialogue rules), uncommitted. Committed tests: unit coverage in
  `test_narration_graph.py`, full-path integration in `test_stage1_api.py`
  (commit → narrator input → persisted attributed output → feed reload,
  fallback, duplicate replay).
- API: working-tree source on `127.0.0.1:18101` against scratch database
  `embervale_live5` (head `0038_preset_creation_receipt`, stage0-v1).
  Scratch database dropped after the session; user compose stack untouched.
- UI: `vite dev --port 5174` proxied to `:18101` (temporary `vite.config.ts`
  edit, restored afterwards).
- Pin: openrouter profile rev 2 (`deepseek/deepseek-v4-flash-0731`,
  temperature 0.2, max_tokens 4096). Key from local `.env`, never evidenced.
- Story: Player as Wren with Wren and Ash at Hearth, world
  `440ac04d-9ac0-4ecf-bb78-907ed2b6728a` (Wren `05a8004f-…`, Ash
  `257a796d-…`).

## Method notes

- Every `audit.json` model-call row carries `call_id`, `phase_run_id`,
  `task_run_id`, `actor_id`, and `created_at`; beat attribution is explicit.
- The beat-1 driver hit a client-side headers timeout after the server had
  the beat in flight; the beat committed and all findings below come from
  the database audit, not the lost driver report.

## Files

- `audit.json` — associations, failure detail, intents, attempts, reactions,
  resolutions, narration.
- `room-b1.png` — beat-1 feed with the DIALOGUE beat ("Market").
- `room-b2.png`, `room-reload.png` — beat-2 feed and fresh-load reload.
