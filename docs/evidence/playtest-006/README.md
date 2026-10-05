# Playtest 006 — the director adds a character (d9ae713)

Same setup as 001–005, 10 live beats, ≈ $0.02. Chronicle in `chronicle.json`.

- **Beat 1:** the director opens "A strange gleam at the Market" and spawns
  **Rollo**, a trader with a glowing stone, at the Market. The hook names
  Wren, Ash and Rollo.
- **Beats 2–3:** Wren and Ash go to the Market together (they meet there) and
  ask to see the stone. Rollo acts from beat 2, as designed (not sealed into
  beat 1).
- **Beats 6–10:** a real three-way exchange: the cave the stone came from,
  a price ("ten silvers each"), a dawn departure, directions ("past the old
  oak by the stream, a half-day's walk north"). All three end at the Market.
- **Repairs:** 4 of ~70 calls (a reaction topic over 256 characters, one
  director and one resolver shape slip).

Next limits this exposes: the cave is not a place (no `new_location`), and
there is no money or item to pay with — items land in the next change.
