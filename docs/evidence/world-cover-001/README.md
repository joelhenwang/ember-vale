# World cover 001

A world's own picture, imported and framed in the world studio (headless
Edge against the dev stack), on "Ember Vale copy" (published as rev 24).

1. `2-framer.png`: the 16:7 banner frame on the imported picture, moved up.
2. `3-check.png`: the check step; a taller box (story card) widens the frame
   around its centre instead of stretching it.
3. `4-card-set.png`: the studio card once the picture is set.
4. `5-library.png`: the library card shows it (the built-in world keeps its
   stock slot).
5. `6-new-story.png`, `7-new-story-phone.png`: the world list in a new story,
   with the picture beside the text, stacked above it on a phone.

Stories made from the world keep a copy of the picture and its frame
(`StoryDetail.cover_asset_id`, `cover_frame`); story cards, recent stories
and the home banner show it. That part is covered by
`test_a_world_picture_becomes_its_stories_cover` and `records.spec.ts`, not
by a story made here. The new-story page's 222 px phone overflow is older
than this change.
