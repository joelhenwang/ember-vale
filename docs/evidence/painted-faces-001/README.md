# Painted faces 001

Backfill of face frames on every painted portrait in the dev database, with
`backend/scripts/frame_painted_faces.py` (the same `frame_face` step the
image runner now takes after painting a portrait).

- Model: openai/gpt-6-luna (the map reader's places model), `FACE_PROMPT`.
- 29 portraits read, 29 faces found; $0.00447 in all, about 4.7 s each.
- `faces.png`: each portrait with its face frame drawn as the round token
  shows it. All 29 sit on the face, with room around it (the found box
  plus 25%, as the framer does); the dog's is on its head.
- `report.json`: the frames written to each story's `portrait_frames`.

Painted portraits are square, so the 2:3 portrait frame is their middle
third-wide crop (the same crop cards already showed).
- `tokens-world.png`: the story-watch map afterwards; the three tokens at the Market show faces.
