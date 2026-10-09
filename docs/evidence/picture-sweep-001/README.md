# picture-sweep-001: pictures no story uses any more are cleaned up

## Question

Going back to a turn (rewind-001) deletes the pictures of removed scenes with
their jobs and asset rows, but never their files, because a branch may show
the same file through its own row. A painting that finishes after its job was
removed also leaves a file behind. Can we delete exactly the files nothing
refers to, without ever losing one that a story, branch, library entry or
backup still needs? And what does the image runner do when its job disappears
mid-paint?

## Where a stored file can be referenced

- Every picture file is written by one of three writers: the image runner
  (`generated/<world|shared>/<kind>-<job>.<ext>`), library uploads and maps
  (`routes/world_maps.py`, `generated/<folder>/<asset id>.<ext>`), and picture
  variants (`asset_cache.py`, `generated/.variants/<asset id>-w<width>.webp`).
  Each original gets an `asset_record` row. Story creation and branches copy
  rows and keep the `content_ref`, so they share the file. Presets, maps, place
  maps, covers and portraits refer to asset **ids**, never to paths.
- Check on the dev DB: every `text`, `varchar`, `json` and `jsonb` column of
  every table was searched for `generated/`. Only `asset_record.content_ref`
  matched (21 rows). No other column is named like a ref, path, file or URL.
- So a file is in use when any `asset_record` row has it as its `content_ref`.
  A variant is in use while its asset row (by id) exists.

## What the sweep does (`infrastructure/images/sweep.py`)

It runs from the background loops (API, or `worldsim.interfaces.worker`): once
at start, then every `WORLDSIM_IMAGES__SWEEP_EVERY_HOURS` (6). It is on by
default and can be turned off with `WORLDSIM_IMAGES__SWEEP_UNUSED=false`.

What it keeps, and why:

| Kept | Why |
|---|---|
| Anything outside `content/assets/generated` | The starter art (`revamp/`) and everything else belongs to the repo or image |
| Files referenced by any row, in any world or the library | Branches share files; library rows have no world |
| Matches that differ only in case | A doubtful match keeps the file |
| Files younger than `SWEEP_GRACE_HOURS` (1) | A job or upload writes the file before its row commits |
| Files that were not already unused at the previous sweep | The first sweep after a start deletes nothing. A file goes only after being unused for a whole interval (6–12 h), so a backup (DB dumped first, pictures second) never loses a picture its dump refers to |
| Everything, when the DB has no asset rows while files exist | An empty or wrong database must not empty the folder |
| Symlinks, and paths that resolve outside `generated/` | Never followed, never deleted |

The DB is read after the folder is listed, so a row added during the listing
still protects its file. Deleting an already-deleted file counts as done, so
two processes may sweep side by side. Any failure only logs. Each sweep logs
the counts and the MB freed.

## The image runner when its job disappears mid-paint

Before: `FixtureImageGateway.complete` raised NOT_FOUND (or, in a narrow race,
the ORM update hit a deleted row). `run_once` raised, `run_forever` logged
"image runner tick failed" with a traceback, and the file stayed on disk with
nothing referring to it. No row came back, because the asset insert rolled
back with the failed job save.

Now (`runner._job_gone`): if finishing fails because the job was removed or
changed meanwhile (NOT_FOUND, PRECONDITION_FAILED, VERSION_CONFLICT, or
StaleDataError), the runner logs one info line and returns. It records
nothing and leaves the file to the sweep. The same applies to `note_attempt`
after a failed paint, and to the repaint swap when the scene picture is gone.

## Tests (`backend/tests/test_picture_sweep.py`)

- `test_only_long_unused_generated_files_go`: covers a kept file, a file a
  branch shares, a library map, a case-only mismatch, a live variant, a young
  file and starter art outside `generated/`. These all stay. A rewound
  picture, an orphan variant and a stale `.part` file wait one sweep and then
  go (bytes freed are counted). The young file goes two sweeps after it ages.
- `test_a_file_used_again_before_the_second_sweep_stays`: a file that gets a
  row between two sweeps is kept.
- `test_an_empty_database_deletes_nothing`: with no rows, two sweeps refuse.
- `test_a_job_removed_while_painting_leaves_only_a_file_for_the_sweep`: the
  story's jobs are deleted while the painter works. `run_once` does not raise.
  No job or asset row comes back, the painted file is the only trace, and two
  sweeps later it is gone. Without the runner change this test fails.

## Numbers (dev data, dry run only, nothing deleted)

Measured in the dev API container against the real dev DB and volume, with
read-only code:

| | files | MB |
|---|---|---|
| originals in use | 14 | 2.6 |
| variants in use | 16 | 0.8 |
| unused | 0 | 0 |

That is 51 asset rows and 30 files. Listing the folder took 9 ms and the
query 244 ms (a cold connection). The dev data was rebuilt after the
2026-10-08 wipe and no rewind on it has removed a picture yet, so there is
nothing to sweep. All 51 rows have their file.

Note: the old map PNGs that `scripts/maps_to_webp.py` deliberately kept next
to their WebP copies are unreferenced. The sweep will delete them wherever
they still exist.

## Verdict

Shipped, on by default. Dry run:
`MSYS_NO_PATHCONV=1 docker compose exec -T -e PICTURE_SWEEP_ROOT=/app/content/assets api python - < backend/scripts/picture_sweep.py`
(add `-e PICTURE_SWEEP_LIST=1` to list the files). This works once the API
image includes this change.
