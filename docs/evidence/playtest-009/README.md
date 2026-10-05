# Playtest 009 — quiet fast-forward and waiting chains (dc320e0)

12 live beats (to Day 2, morning), 15 s between beats, ≈ $0.03.
Chronicle in `chronicle.json`.

- **No quiet beat occurred:** every beat had at least one non-idle scene, so
  the fast-forward and feed folding were not exercised live (covered by
  tests). Beat gaps were the configured 15 s throughout.
- **Director:** spawned **Old Bram** with "The Trader's Tale" (a disputed
  coin) at beat 4; an earlier proposal used `name` instead of `title` and was
  rejected; three later `noop`s ("actively resolving").
- **Beats 4–6:** Wren and Ash walk to the Market together, meet Bram, and
  start on the coin dispute — the coin's edge, a flame-and-spade sigil, an
  old forge's mark.
- **Beats 6–12: a conversation loop.** Everyone asks Bram "to continue the
  full tale"; Bram answers with topics ("The full tale of the forge's mark")
  but never tells it, so nothing new is learned for seven beats. The waiting-
  chain rule does not catch it: everyone is "engaged".
- **Repairs:** 9 (narrator 5 — dialogue not quoting its cited speech; resolver
  2; director 1; reaction 1), up from 1–4 in quieter runs.

**Findings:** (1) a talk loop needs its own guard — characters should not
re-ask what they already asked, and a character asked for knowledge should
say it (quoted, concrete) rather than name it; (2) the director should see
repetition (the same topic beat after beat) as a stall; (3) narrator repairs
grow with dialogue density.
