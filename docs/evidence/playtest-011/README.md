# Playtest 011 — interact and a resolver that can see (7c81df3)

12 live beats, ≈ $0.03. Chronicle in `chronicle.json`.

- **A small mystery:** the director places a **lost purse** with a shopping
  list at the Hearth, then spawns **Marta the festival baker** (missing flour)
  and **Pip** with the miller's son's ledger. Clues pile up: a frayed/cut
  cord, flour "already delivered last week", the purse is Elara's, a plan to
  check Dryden's mill.
- **interact used for real:** Ash examines the purse (`interact`), Wren calls
  out at the stalls; the resolver judges each (11 success, 3 partial).
- **But the purse never moved:** Ash "picks it up" with `interact` instead of
  `take`, so it still lies at the Hearth while they read its list. Prompt
  character_decision.v7 now says take/transfer move items, interact never does.
- **Dryden's mill does not exist** — the characters invented it in talk; the
  director did not add it.
- **Repairs:** 13, of which 8 were reaction lines over the 256-character topic
  limit — a side effect of "say concrete things". Spoken lines may now be 400
  characters; observation text is clipped to its 512-character limit.
