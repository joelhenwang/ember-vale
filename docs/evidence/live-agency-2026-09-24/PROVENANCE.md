# Player agency — enforcement check, live round 9, 2026-09-24 (UTC)

## Claim

With controlled-character enforcement live, an ordinary UI-created,
pinned Player-as-Wren story commits the player's submitted question and
Ash's quoted answer, while no model-authored decision, reaction, action,
or speech for Wren reaches any model call, proposal, or committed row:

- Q1 ("What does the Market hold today?", Speak-as-Wren → Ash): Wren's
  intent committed normally; Ash's reaction answered `communicate` with
  Wren's real ID and a literally quoted topic; fallback persisted a
  `dialogue` beat with Ash's speaker ID and reaction citation (narrator
  exhausted its budget again). The room displays "Ash: The stalls are
  stirring, …".
- The audit shows zero model calls with Wren as actor in decision or
  reaction roles, zero committed reactions with Wren as reactor, and zero
  Wren attempts beyond the player-intent attempt. Round 8's failure mode
  (model-voiced "See anything good?" for player-controlled Wren) cannot
  recur through these paths: no call is even placed.
- Reload: fresh page load shows the identical 6 feed entries, no
  duplication, zero page errors throughout.

Record narrowly: **player-submitted speech commits and receives answers;
model-generated speech and actions for the controlled character are
prevented before commitment, with ownership resolved from the persisted
grant once per run.**

## Provenance

- Source: working tree at `72f4195` with the agency change uncommitted:
  `resolve_controlled_character` (grant → owner), `PhaseRuntime.
  controlled_character_id` resolved in `_runtime`, proposal skips in
  `_decide_one`/`_decide_all` and `_react_all`. Committed tests: 4 new
  checks in `test_stage1_orchestration.py` (no-model-proposals,
  reload-and-retry ownership, grant resolution ×2).
- API: working-tree source on `127.0.0.1:18101` against scratch database
  `embervale_live8_main_85bf5d62` (template clone; both dropped after the
  session; user compose stack untouched).
- UI: `vite dev --port 5174` proxied to `:18101` (temporary
  `vite.config.ts` target edit, restored afterwards).
- Pin: connection `5a0e5f29-…` (`ui8-live`, openrouter) with profile rev 2
  (`3655c774-…`, `deepseek/deepseek-v4-flash-0731`, temperature 0.2,
  max_tokens 4096), selected through the wizard's pin picker. Every call
  transmitted `max_tokens 4096`; no override anywhere.
- Story: `a06c1eff-e14a-466e-b3ec-a64de1e5f96d`, quickstarted in the
  browser, edited to Player as Wren with pin rev 2. Beat 1: Wren journeys
  Hearth → Market; beat 2: Speak-as question. Seat bound throughout.
- Driver: headless Edge via `playwright-core` (`tmp-ui8b/`, deleted after
  the run); no request mediation, no payload or sampling patches.

## Results

- 7 model calls, 6 succeeded, all on `deepseek/deepseek-v4-flash-0731`.
  The single failure is the known mode: narrator `reasoning_only` to
  budget length. Failed attempt preserved with call ID and associations.
- Beat 1: director + one character decision (Ash only). Beat 2: decision
  (Ash), two Ash reactions (one committed answer), resolver, narrator
  failed → fallback dialogue.
- Directed intents, resolution effects (the journey move applied to Wren),
  NPC autonomy (Ash decides/reacts), and no-grant automatic behavior are
  untouched — the skip applies only to model-authored proposals for the
  granted character. Existing suites covering those paths still pass.
- Involuntary consequences preserved by construction: enforcement sits at
  proposal time (no model call placed), never at the commit boundary, so
  resolution effects targeting Wren still apply.

## Files

- `audit.json` — characters, story setup (pin), connections, profile
  revisions, per-beat runs, intents, attempts, reactions, resolutions,
  narration, and full call rows.
- `ui-ai.png` — step-5 pin selection (ui8-live, rev 2).
- `ui-review.png` — review (Player as Wren; Storyteller rev 2).
- `ui-room-b1.png` — post-journey room (Wren at Market).
- `ui-room-b2.png` — Q1 answer attributed to Ash.
- `ui-room-reload.png` — fresh-load feed, identical.
