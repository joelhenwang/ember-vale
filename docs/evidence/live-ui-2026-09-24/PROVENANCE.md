# Dialogue delivery — ordinary-flow closure, live round 8, 2026-09-24 (UTC)

## Claim

One Player-as-Wren story, created entirely through the UI and pinned to an
existing provider profile revision through the wizard's own pin picker,
delivered quoted NPC dialogue to the browser with speaker attribution:

- Q1 ("What does the Market hold today?", Speak-as-Wren → Ash): Ash's
  reaction answered `communicate` with Wren's real ID and a literally quoted
  topic. The model narrator exhausted its budget, and the deterministic
  fallback persisted a `dialogue` beat with Ash's speaker ID citing that
  reaction. The room displays "Ash: Depends what you're buying. …".
- Follow-up ("You mentioned honest bargains — where exactly should I
  look?"): no second NPC answer appeared. Ash elected `observe`; his
  reaction call burned the full budget reasoning and failed. The model
  voiced a quoted reaction *as Wren* ("See anything good?"), and the
  fallback (narrator also failed) persisted it as a `Wren:` dialogue beat
  alongside the attempt echoes.
- Reload: a fresh page load shows the identical 9 feed entries —
  byte-identical feed text, no duplication, zero page errors throughout.

Record narrowly: **quoted NPC dialogue persisted with speaker attribution
and reaction citation, rendered in the browser, and surviving reload —
through the ordinary pinned-story flow with no harness override.** The
follow-up exchange is coherent in form but produced no new NPC answer, so
conversation memory remains unverified (as before).

## Provenance

- Source: clean tree at `4e1f568` (43rd push); no source changes for this
  round. Commit identity recorded before the run; the only tree edit was
  the temporary dev-proxy target, restored afterwards.
- API: working-tree source on `127.0.0.1:18101` against scratch database
  `embervale_live8_main_0991f58b` (template clone, migrated to head;
  both dropped after the session; user compose stack untouched).
- UI: `vite dev --port 5174` proxied to `:18101` (temporary
  `vite.config.ts` target edit, restored afterwards; key injected by the
  existing dev proxy from local `.env`, never held by the browser).
- Pin: connection `72c015cb-…` (`ui8-live`, openrouter, credential resolves
  from environment) with profile rev 2 (`8702a43e-…`,
  `deepseek/deepseek-v4-flash-0731`, temperature 0.2, max_tokens 4096),
  provisioned via the settings API (no creation UI exists) and **selected
  through the wizard's step-5 pin picker**. The story setup snapshot pins
  `profile_id 8702a43e-…` rev 2; every executed call transmitted
  `max_tokens 4096` with no override anywhere.
- Story: `e3cca38e-533b-49b4-979f-626d608035ed` ("A Morning in Ember Vale"),
  quickstarted in the browser, then edited in the wizard: Player as Wren,
  cast Ash (starts Market) + Wren (starts Hearth), pin rev 2. Beat 1:
  Wren journeys Hearth → Market (ordinary travel UI), committed; beats 2–3:
  Speak-as questions committed from the room. Seat bound to the player
  throughout ("The player's seat is bound").
- Driver: headless Edge via `playwright-core` (`tmp-ui8/`, deleted after
  the run); no request mediation, no payload or sampling patches.

## Results

- 15 model calls, 10 succeeded, all on
  `deepseek/deepseek-v4-flash-0731` under the pinned rev-2 budget. All 5
  failures are one mode: `reasoning_only` until `finish_reason length`
  (full 4096-token budget burned on reasoning, zero content) — Ash's
  beat-2 decision, Wren's beat-2 reaction, both narrators, and Ash's
  beat-3 reaction. Failed attempts preserved in `audit.json` with call
  IDs, phase/task/actor associations, and raw result detail.
- Beat 2: intents Ash-wait + Wren-communicate; both attempts committed; 2
  reaction calls succeeded but only Ash's answer committed: Wren's attempt
  at a reaction returned schema-invalid text (`{": ": ", "}`) and its repair
  call then burned the full budget reasoning — a validation/provider
  failure, not a character choice; resolver ok; narrator failed →
  fallback `dialogue` (Ash, cited `reaction:6b30d3ce-…`).
- Beat 3: intents Ash-observe + Wren-communicate; Wren's quoted reaction to
  Ash's observe committed ("See anything good?"); Ash's reaction failed;
  resolver ok; narrator failed → fallback `dialogue` (Wren, cited
  `reaction:7bf40bd1-…`) plus attempt echoes.
- The model spoke *as the player character* in a reaction (Wren reacting to
  Ash's observe). That is existing orchestration behavior, recorded, not
  changed in this slice.
- The room banner still claims "beats are deterministic stand-ins" while a
  live pin is active — the banner describes the environment default, not
  the pinned story. Product nit, left untouched per scope.

## Milestone

> Quoted NPC dialogue delivered through an ordinary UI-created, pinned
> story, with speaker attribution, source citations, and browser reload
> persistence. Sustained conversation and conversation memory remain
> unverified.

## Stop-condition verdict

The flow passes: ordinary UI story creation, existing-pin selection with
the intended budget, quoted answer committed → DIALOGUE with speaker ID
and citation → visibly attributed in the browser → reload-identical
without duplication. **Dialogue delivery is closed.** Recommended next:
reliability (reasoning-exhaustion rate at pin budgets) and storytelling
quality. Conversation-memory verification remains a separate, pending
check. No correction is proposed: no stage failed.

## Files

- `audit.json` — characters, story setup (pin), connections, profile
  revisions, per-beat runs, intents, attempts, reactions, resolutions,
  narration, and full call rows (IDs, associations, sampling, outcomes,
  raw result text/detail).
- `ui-ai.png` — step-5 pin selection (ui8-live, rev 2).
- `ui-review.png` — review (Player as Wren; Storyteller ui8-live rev 2).
- `ui-room-b1.png` — post-journey room (Wren at Market).
- `ui-room-b2.png` — Q1 answer attributed to Ash.
- `ui-room-b3.png` — follow-up beat (Wren dialogue, no Ash answer).
- `ui-room-reload.png` — fresh-load feed, identical.
