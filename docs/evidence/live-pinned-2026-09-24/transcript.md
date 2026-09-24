# Transcript — live pinned session 2026-09-24

Story A `a49aa6d8-…` ("Live pinned dialogue", observer, Wren + Ash),
pin `deepseek/deepseek-chat` rev 2, temp 0.2. All beats committed in the
browser at `/stories/…/play`.

- Beat 1 — `ACTION RESOLVED / attempt:wait: Ash waits`, `… Wren waits`,
  `WORLD TICKED`. Calls: director + 2× character_decision, all
  `pin-284533dd-r2` succeeded.
- Beats 2–4 — same WAIT shape, distinct voices. Beat-4 replay returned
  `duplicate=True`.
- Direction (God seat, force): "Wren turns to Ash at the Hearth and asks
  where the north road leads" → `needs_clarification` with live text:
  "The instruction says Wren turns to Ash 'at the Hearth', but Ash is
  currently at Market while Wren is at Hearth — they are in different
  locations. Did you mean: (a) Ash travels to the Hearth first … (b) …
  (c) … Also note that 'where the north road leads' is a question about
  world lore with no established answer in context…" (`shots/16-…`).
- Follow-up filings (travel, ID-explicit question): generic mapping
  fallback — free-pool flakiness, no recorded interpret calls.
- Beat 5, beat 6 — WAIT shape, pin-identity holds throughout.

Story B `c27f4ba0-…` (same setup), pin rev 3, temp 1.0:

- Beats 1–3 — WAIT shape; all calls `pin-6e790d13-r3` succeeded.
- Reload: 10 feed entries matched persisted events; beat 4 added exactly
  3 entries (13 total), no duplicates (`shots/30-…`, `31-…`).

Persisted `narration` rows equal the visible feed verbatim
(`attempt:wait: …`). No NPC dialogue prose was generated in either story:
at both temperatures the model elected WAIT in this quiet opening.
