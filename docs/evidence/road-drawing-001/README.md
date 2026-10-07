# Road drawing 001

Drawing a world by hand on the map page, in headless Edge against the dev
stack (`run.mjs`), on a fresh copy of the built-in world (preset
aa12c4f2…, "Ember Vale copy"). No map reader and no picture: everything
here is put down by hand on a blank parchment.

1. `1-places.png`: Blank parchment, then three places added by clicking:
   Hearth and Market (matched to the world's places) and a new Old Mill.
2. `2-drawing.png`: Draw a road from Hearth: three bends clicked, one taken
   back with Backspace and clicked again; the pointer near Market snaps
   to it (the gold ring) and the dashed stretch ends on it.
3. Run output (the clicks): the road is drawn with 3 bends; Hearth to Old
   Mill straight; Old Mill to Market with one bend; a second road between
   Market and Hearth is refused ("There is already a road between Market
   and Hearth."); Esc stops drawing, a second Esc leaves the tool.
4. `3-editing.png`: Hearth to Old Mill selected: a bend pulled out of the
   middle of a stretch (hollow dots), then removed by double-click and
   pulled out again.
5. `4-roads-table.png`, `5-saved.png`: saved, then reloaded: 3 pins and 3
   roads with their bends, timed from their drawn length.
6. `studio-big.png`: the world studio's Map tab now shows the world's own
   map with its places and roads (here the 15-place "Ember Vale copy").

At 400 px wide the map page does not scroll sideways.
