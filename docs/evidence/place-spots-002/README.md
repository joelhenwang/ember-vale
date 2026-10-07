# place-spots-002: spot names a story can use, on painted pictures

**Why.** "Inside every place at once" paints each place with Krea, which writes no labels.
With the place-spots-001 prompt ("otherwise a short description") Luna then named spots by
their position in the picture ("Large foreground house near the bottom center", "House just
southwest of the plaza"), which reads badly in a scene, and listed every house: Market's
picture went over the 32-spot limit and failed to save (HTTP 422).

**Change.** `SPOTS_PROMPT`: list each distinct spot once, ordinary houses only when one stands
out (at most three); an unlabelled spot gets "a short name a local would call it by, from what
it is and how it looks", never words about the picture (left, right, foreground, centre…).
Old prompt kept as `spots-v1.txt`.

**Pictures.** `pictures/` holds three Krea paintings made by the batch for "Ember Vale copy"
(Tidemark, a port; Blackreef, a castle; Ixquel, a temple; JPEG copies), plus the labelled
village `../map-detect-001/maps/map-5.png` to check that written labels still win.
Script: `backend/scripts/place_spots_eval.py`.

| picture | prompt | spots | plain houses | names with position words |
| --- | --- | --- | --- | --- |
| village (labelled) | v1 | 19 | 3 | 0 |
| village (labelled) | v2 | 15 | 0 | 1 ("Hilltop Cairn") |
| Tidemark | v1 | 59 | 48 | 4 |
| Tidemark | v2 | 15 | 3 | 0 |
| Blackreef | v1 | 16 | 2 | 2 |
| Blackreef | v2 | 13 | 1 | 1 ("High Central Tower") |
| Ixquel | v1 | 12 | 2 | 0 |
| Ixquel | v2 | 14 | 0 | 0 |

v2 names, for the record:

- **Tidemark:** Harbor Square, The Red Spire, The Harbor Pier, The Seawall Walk, The Market
  Stalls, The Town Well, The Bell Tower, The Half-Timbered Inn, The Stone Gatehouse, The Harbor
  Chapel, The Watchtower, The Weavers' House, The Seafarers' House…
- **Village:** every written label kept (the Hearth, Market square, Smithy, Mill, Chapel…), and
  the hilltop cairn every earlier run missed is now found.

Compass names remain ("Northwest Tower", "the Southeast Gatehouse"); they read as in-world
names. Luna borrowed one example ("The Red Spire" next to the prompt's "the Red Tower").

**Cost.** 8 readings, $0.0044.
