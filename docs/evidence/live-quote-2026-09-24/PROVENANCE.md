# Quoted speech — live round 7, 2026-09-24 (UTC)

## Claim

With the quotation convention documented in the reaction prompt, the live
model produced actual attributed speech end to end: question → quoted
answer → answer-dependent follow-up → second quoted answer → reload.

- Beat 2 (Q1 "What does the Market hold today?", Wren → Ash): Ash's
  reaction answered `communicate` with Wren's real ID and a literally
  quoted topic (`"Today the Market holds more gossip than silver, but the
  pie seller is still doing fine."`). The model narrator rendered a
  `dialogue` beat with Ash's speaker ID citing that reaction. No fallback
  involved.
- Beat 3 (follow-up "You mentioned the pie seller — which pies does he
  sell today?"): Ash answered `"Apple and mutton — though the mutton's
  mostly gristle and hope today."`, again quoted with Wren's real ID. The
  model narrator exhausted its budget reasoning, and the deterministic
  fallback persisted the `dialogue` beat with Ash's speaker ID and the
  reaction citation.
- Reload: fresh-client `scenes` + `scenes/{id}/narration` reads match the
  committed beats exactly (beat 2: 3 beats; beat 3: 5 beats).

Record narrowly: **quoted NPC answers committed as DIALOGUE beats with the
speaker ID, retrieved through the feed path, and identical on reload.**
The follow-up is answer-dependent in form (pies ← pie seller), but it
explicitly re-supplies "the pie seller", so the model could answer without
retrieving the earlier answer: this proves a coherent answer-dependent
exchange, not remembered conversation.

## Milestone

> Live quoted NPC dialogue persisted with speaker attribution and source
> citations, including narrator-outage fallback. A coherent follow-up
> exchange was demonstrated through the API. Browser verification of quoted
> dialogue and conversation-memory verification remain pending.

## Provenance

- Source: working tree past `dffe62a` (41st push) with the
  reaction-prompt quotation paragraph uncommitted, plus the prompt-content
  test in `test_reaction_graph.py`. No other source changes.
- API: working-tree source via in-process TestClient against scratch
  database (template + clone, both dropped after the session; user compose
  stack untouched). Seed: stage0 (`content/seeds/stage0`), world
  `10000000-…000001`, Wren `…0101` as the bound player character, Ash
  `…0102`.
- Sampling: the seed path builds pin-less `SamplingParams()` capped at 512
  tokens per call. The harness overrode the default to 4096 per call to
  match the story pin budget of prior live rounds (scratch-script subclass
  swap in the single TestClient process; no repo change). Beat 1 ran at the
  stock 512 budget and is kept as evidence of the exhaustion failure mode.
- Pin/model: no story pin on this path; every executed call ran on
  `deepseek/deepseek-v4-flash-0731` (cost rows in `audit.json`). Key from
  local `.env`, never evidenced.

## Results

- Beat 1 (512 budget): director ok; decision, both reactions, resolver,
  narrator all `malformed` — `reasoning_only`, full budget burned on
  reasoning, zero content. Only attempt-echo narration committed. The
  default budget cannot carry this model's reasoning for any role except
  the director.
- Beat 2 (4096): 4/5 calls succeeded (no director call in this run).
  Ash quoted; Wren's own reaction burned all 4096 tokens reasoning and
  failed. Resolver and model narrator succeeded; `dialogue` beat with
  Ash's speaker ID persisted and reloaded identically.
- Beat 3 (4096): 6/7 calls succeeded. Ash produced two quoted communicates;
  one carried a corrupted family key (`"": "communicate"`) and was
  rejected by validation — only the well-formed "Apple and mutton" answer
  committed. Narrator exhausted its budget (4361 reasoning tokens), so the
  `dialogue` beat is deterministic fallback with speaker + citation.
- Totals: 18 calls, 11 succeeded; 2 quoted Ash answers committed; 2
  `DIALOGUE` beats with Ash's speaker ID (one model-voiced, one fallback),
  both reload-identical.

## Honest notes

- `character_decision` outputs on this path are degenerate (zero/`unknown`
  IDs, wait/observe) yet runs complete; the player intent drives the
  scenes. Not diagnosed further — outside this slice.
- Wren's beat-2 reaction failure and the beat-3 narrator outage show the
  provider still exhausts budgets mid-run; attribution survived both via
  commit-then-voice ordering and the fallback, respectively.
- Feed proof is API-level (`scenes`/`narration` endpoint reads) on an
  unpinned seed world with a locally overridden token budget: it establishes
  persisted dialogue retrieval — not a new browser demonstration, and not
  verification of normal pinned-story configuration. The seed world has no
  UI story, and round 6 already showed the UI's speaker-prefixed rendering.
  The duplicate "Ash: Ash speaks" prefix remains cosmetic.
- This round's `audit.json` omits per-call IDs, phase/task/actor
  associations, and raw result payloads (the scratch databases were dropped
  before the export was extended), so the failure-cause claims above rest
  on throwaway diagnostics and are less independently checkable than the
  round-5/6 exports. Future live exports must retain call IDs,
  actor/task associations, and diagnostic detail.
- Beat 1's 512-budget collapse is a harness-setting observation, not a
  product claim: production stories run under pin budgets.

## Files

- `audit.json` — world, characters, model, per-beat intents, calls,
  reactions, and narration rows.
