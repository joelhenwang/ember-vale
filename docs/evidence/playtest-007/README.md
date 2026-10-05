# Playtest 007 — items (66f08a5)

Same setup, 10 live beats, ≈ $0.02. Chronicle in `chronicle.json`.

- **Director:** "A Stray Cart Blocks the Market Gate" spawns **Old Bramble**
  (the cart's owner) at the Market; "A Wheelwright's Business Card" places
  a **Wheelwright's card** at the Market; a third hook, "Wheelwright's shop
  shuttered", names a shop that does not exist.
- **Characters:** Wren and Ash go to the Market together, Wren examines the
  card (observe), Bramble suggests fetching the wheelwright, all three agree.
  Nobody takes the card (it still lies at the Market).
- **Then the story leaves the map:** "head to the forge", "fetch the
  wheelwright" — neither exists. Ash shuttles Hearth ↔ Market looking for
  it; by beat 10 everyone waits.
- Repairs: 2 (one director shape — a proposal plus a `noop` key — and one
  narrator speaker outside the audience).

**Finding:** openings and characters keep reaching for places beyond the two
on the map (a cave in 006, a forge here). Next step: let the director add a
place (`new_location`, already an allowed power but never implemented) with
a route from an existing place, and tell it that openings must be reachable.
