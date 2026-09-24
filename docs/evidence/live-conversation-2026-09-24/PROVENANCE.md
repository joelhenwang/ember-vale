# Focused conversation run — live round 4, 2026-09-24 (UTC)

## Claim

With the `known_characters` roster fix live, Ash's reaction model produced a
schema-valid `communicate` answer carrying **Wren's real ID**, which passed
identity validation and **persisted as a committed reaction row** — the
first live NPC answer through validation to durability. It is not yet a
conversation: the answer never reaches narration or the browser.

Step-by-step against the assigned proof:

1. **Call associations exported.** Every `audit.json` model-call row carries
   `call_id`, `phase_run_id`, `task_run_id`, `actor_id`, and `created_at`.
   Beat attribution is explicit; no positional inference is needed.
2. **Ash received Wren's actual ID in the prompt.** Verified against the
   stored request of Ash's reaction call (`actor_id` = Ash): the prompt
   contains the roster `- Ash (id: 588734ed-…)`, `- Wren (id:
   905f2078-…)` with both live UUIDs.
3. **Ash's response traced through validation to persistence.** Beat-2
   reaction call (11:01:52, actor Ash) returned `communicate` with
   `target_character_id` = Wren's real ID and topic "The Market holds
   stalls, wind, and trade; tell me what you're after and I'll point you
   true." Schema PASS, `precheck_action` PASS (target in the validated
   set), first attempt (no repair rows), persisted as a `reaction` row:
   reactor Ash, status `committed`.
4. **FAILED — NPC dialogue not displayed, no Ash speaker ID.** The exact
   failing stage is narration input: `_narrate_scene` builds the narrator
   call from event-observation facts only (`visible_facts`); committed
   reactions are written to canon and readable via the scene API
   (`reactions_for_scene`) but are never passed to the narration graph, so
   narration-backed feed cannot voice them. All persisted narration rows
   have `speaker_character_id` null. Reload survival verified for what is
   displayed (feed identical across a fresh page load, zero page errors).
5. **Follow-up asked, continuity partial.** Q2 ("ask Ash again what the
   Market holds") committed with provider 5/5; question continuity holds.
   Answer continuity is N/A — no NPC answer was ever voiced.

## Provenance

- Source: working tree at `cdc61fb` (38th push) including the roster fix,
  uncommitted; no source changes made during this run.
- API: working-tree source on `127.0.0.1:18101` against scratch database
  `embervale_live4` (head `0038_preset_creation_receipt`, stage0-v1).
  Scratch database dropped after the session; user compose stack untouched.
- UI: `vite dev --port 5174` proxied to `:18101` (temporary `vite.config.ts`
  edit, restored afterwards). One vite instance crashed on a watcher EBUSY
  from a scratch driver file placed in the watched root; the file was
  removed, the server restarted clean, and drivers now import
  playwright-core by absolute path from outside the root.
- Pin: openrouter profile rev 2 (`deepseek/deepseek-v4-flash-0731`,
  temperature 0.2, max_tokens 4096). Key from local `.env`, never evidenced.
- Story: Player as Wren with Wren and Ash at Hearth, world
  `3a74f93f-3d94-4678-b935-12224cfd0d69` (Wren `905f2078-…`, Ash
  `588734ed-…`).

## Results, by stage

- Beat 1 (Q1 "what the Market holds"): 3/6 provider (director, decision,
  resolver ok; both reactions + narrator `malformed` with
  `reasoning_only: true`). Resolution `success` via model; fallback
  narration ("Ash waits"). No reaction rows.
- Beat 2 (Q2 follow-up): 5/5 provider (decision, reaction ×2, resolver,
  narrator). Ash's reaction persisted as above; Wren's own reaction WAIT
  also committed. Narration: "Wren asks again… Ash waits again" — the
  narrator voiced attempts only.
- Totals: 11 calls, 8 succeeded; 2 committed reactions (Ash communicate,
  Wren wait); 8 narration rows, all speaker null.
- Browser: `room-b1.png`, `room-b2.png` (both beats in feed), and
  `room-reload.png` (fresh load, identical feed), all zero page errors. No
  Ash-spoken line appears anywhere in the UI.

## Files

- `audit.json` — world/character ids, model calls with associations and
  failure detail, intents, attempts, reactions, resolutions, narration.
- `room-b1.png`, `room-b2.png`, `room-reload.png` — feed after each beat
  and after reload.
