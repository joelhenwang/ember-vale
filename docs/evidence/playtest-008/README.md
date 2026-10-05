# Playtest 008 — director-added places (0112d48)

Same setup, 10 live beats, ≈ $0.02. Chronicle in `chronicle.json`.

- **Beat 1:** "A Stranger's Broken Cart" spawns **Old Man Bramble** outside the
  Hearth; he needs someone to watch his cart while he fetches a wheelwright
  from the Market. No new place was needed (the opening used the Market), so
  `new_location` was not exercised live; it is covered by
  `tests/test_director_places.py`.
- **Beats 2–4:** Bramble asks for help; Wren agrees to watch the cart; Ash goes
  to the Market and back.
- **Beats 5–9 (sunset to midnight): everyone waits.** Intentions:
  Wren "Wait for morning…", Ash "watch over Bramble's cart until he returns",
  Bramble "Wait for Ash and Wren to help watch the cart so I can go". Each
  waits on the other — a small deadlock — and night makes waiting plausible.
  The director saw the idle streak and declined three times ("the evening is
  quiet… purpose for the next day").
- **Beat 10:** Bramble finally heads to the Market.
- Repairs: 1 (narrator over the beat budget).

**Findings:** (1) quiet night phases make a watch-along dull — candidates:
fast-forward phases where everyone only waits, or let characters rest through
the night; (2) mutual waiting is not detected — the director could treat a
waiting chain as idle rather than "a task in progress".
