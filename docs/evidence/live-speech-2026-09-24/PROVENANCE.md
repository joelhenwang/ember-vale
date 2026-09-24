# Speech contract — live round 6, 2026-09-24 (UTC)

## Claim

Question → answer → answer-dependent follow-up → reload, with the new
speech contract live: unquoted (instruction-like) topics render as
attributed narrative summaries, never as purported spoken words, and the
feed names the speaker.

- Q1 ("what the Market holds"): beat 4/7 provider (director, both
  reactions, resolver ok; second director, decision, narrator
  `malformed`). Two committed communicates: Wren → Ash ("What are you
  waiting for?") and Ash → Wren ("Market"), both with real target IDs.
  Narrator outage → fallback summaries `Ash speaks to Wren about "Market"`
  and `Wren speaks to Ash about "What are you waiting for?"`, each with its
  speaker ID and reaction citation. No false quotation.
- Q2 ("name the stalls in the Market he mentioned"), built on Ash's
  "Market": beat 3/5 provider (decision, both reactions ok; resolver and
  narrator `malformed`). Ash answered "Market stalls" with Wren's real ID,
  committed; deterministic resolution recorded honest
  `impossible`/provider-failed fallback; fallback summary `Ash speaks to
  Wren about "Market stalls"` persisted with speaker + citation.
- Totals: 12 calls, 7 succeeded; 4 committed reactions; 11 narration rows,
  three of them speaker-attributed summaries.
- Feed (`room-b1/b2/reload.png`, zero page errors throughout): timeline
  snippets prefix spoken beats with the speaker name ("Ash: Ash speaks to
  Wren about …"), and the feed is identical across a fresh page load.

Continuity note: the thread Q1 → A1 ("Market") → Q2 (stalls in "the Market
he mentioned") → A2 ("Market stalls") is answer-dependent in form, but A2
repeats A1's topic, so topical relevance alone does not prove remembered
conversation. No committed `DIALOGUE` beats were produced in this round —
all attributed speech evidence is narration-kind summaries — and at the
time of this run the reaction-generation prompt did not document the
quotation convention, so this run cannot say whether terseness is
provider- or pipeline-caused. Both narrator model calls returned
`malformed`; every voiced beat shown is deterministic fallback narration,
not model narration. Record narrowly: **attributed communication summaries
displayed and survived reload**.

## Provenance

- Source: working tree past `f5c128c` (40th push) with the speech-contract
  change (quoted-utterance identification, says/speaks fact values, speaker
  roster in the narrator prompt, summary fallback, speaker-prefixed feed
  snippets), uncommitted. Committed tests: unit + HTTP integration in
  `test_narration_graph.py` / `test_stage1_api.py`.
- API: working-tree source on `127.0.0.1:18101` against scratch database
  `embervale_live6` (head `0038_preset_creation_receipt`, stage0-v1).
  Scratch database dropped after the session; user compose stack untouched.
- UI: `vite dev --port 5174` proxied to `:18101` (temporary `vite.config.ts`
  edit, restored afterwards).
- Pin: openrouter profile rev 2 (`deepseek/deepseek-v4-flash-0731`,
  temperature 0.2, max_tokens 4096). Key from local `.env`, never evidenced.
- Story: Player as Wren with Wren and Ash at Hearth, world
  `fa766cb1-7cf9-415a-96c1-6b64cd60a5dc` (Wren `515a461d-…`, Ash
  `09a286b3-…`).

## Method notes

- Every `audit.json` model-call row carries `call_id`, `phase_run_id`,
  `task_run_id`, `actor_id`, and `created_at`.
- The beat-1 driver hit a client-side headers timeout while the server had
  the beat in flight; the beat committed and findings come from the
  database audit (kept as a separate driver issue per review).

## Files

- `audit.json` — associations, failure detail, intents, attempts, reactions,
  resolutions, narration.
- `room-b1.png`, `room-b2.png`, `room-reload.png` — feeds and reload proof.
