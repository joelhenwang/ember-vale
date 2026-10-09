"""Turn checkpoints and the branch copy (tables ``story_checkpoint``, ``story_branch``; 0058).

Plain SQL over whole tables: a checkpoint is built inside Postgres in one
statement (``to_jsonb`` of every changeable row of the story), and a branch
reads rows as JSON, renames every id in Python, and writes them back with
``jsonb_populate_recordset``. No row is read into the ORM, so the copy
follows the schema as it is, column for column.

Renaming rule (what keeps a branch apart from its source):

* every key column of a copied row gets a new id (runs and snapshots keep
  their derived form, ``derive_run_id(new world, index)``, so the engine
  finds them again; intents, attempts, reactions and resolutions too);
* a column pointing at a copied row follows it; one pointing at a row of
  the source that is not copied (a model call, a task run) becomes empty;
* ids written inside text and JSON (``journey:<scene hex>:...``,
  ``obs:<uuid>``) are renamed the same way, in both spellings; an id of a
  source row that is not copied gets a fresh stand-in, so nothing in the
  branch names a row of the source;
* an asset's ``content_ref`` is kept: the branch shows the same stored
  file through its own asset row, nothing is duplicated on disk.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain import branches
from worldsim.domain.branches import (
    CHECKPOINT_SCHEMA_VERSION,
    BranchCopy,
    CheckpointHead,
    StoryBranchOrigin,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    derive_attempt_id,
    derive_intent_id,
    derive_reaction_id,
    derive_resolution_id,
)
from worldsim.domain.time import PHASES_PER_DAY

Row = dict[str, Any]

_W = "t.world_id = :w"

#: The story's changeable state, captured whole at the end of every turn.
STATE_TABLES: tuple[tuple[str, str], ...] = (
    ("world", "t.id = :w"),
    ("world_clock", _W),
    ("entity", _W),
    ("location", _W),
    ("character", _W),
    (
        "character_card_version",
        't.character_id IN (SELECT id FROM "character" WHERE world_id = :w)',
    ),
    ("character_state", _W),
    ("character_intention", _W),
    ("travel_route", _W),
    ("item_instance", _W),
    ("relationship", _W),
    ("relationship_evidence", _W),
    ("claim", _W),
    ("belief", _W),
    ("narrative_hook", _W),
    ("narrative_arc", _W),
    ("activity", _W),
    ("scheduled_effect", _W),
    ("world_condition", _W),
    ("skill_definition", _W),
    ("character_skill", _W),
    ("training_session", _W),
    ("role_grant", _W),
    ("focus_assignment", _W),
    ("lineage_character", _W),
    ("lineage_link", _W),
    ("dnd_party_member", _W),
    ("dnd_monster", _W),
    ("aggregate_version", _W),
    ("intervention", _W),
    (
        "intervention_step",
        "t.intervention_id IN (SELECT id FROM intervention WHERE world_id = :w)",
    ),
    ("macro_period_run", _W),
    ("macro_aggregate_effect", _W),
    ("macro_interruption", _W),
    ("end_condition_evidence", _W),
    ("era_summary", _W),
)

#: Config values longer than this are kept as a fingerprint, not repeated
#: every turn: the map, place maps and portrait frames are written when a
#: story is made; a branch takes the live value only if it still matches.
CONFIG_INLINE_CHARS = 2048

_RUNS = "SELECT id FROM phase_run WHERE world_id = :w AND absolute_index <= :n"
_SNAPS = "SELECT id FROM phase_snapshot WHERE world_id = :w AND absolute_index <= :n"
_EVENTS = "SELECT id FROM world_event WHERE world_id = :w AND sequence <= :seq"
_SCENES = f"SELECT id FROM scene WHERE world_id = :w AND phase_run_id IN ({_RUNS})"
_INTENTS = f"SELECT id FROM character_intent WHERE world_id = :w AND snapshot_id IN ({_SNAPS})"
_ATTEMPTS = f"SELECT id FROM attempt WHERE intent_id IN ({_INTENTS})"

#: History that is only added to: copied up to the turn at branch time.
HISTORY_TABLES: tuple[tuple[str, str], ...] = (
    ("phase_run", "t.world_id = :w AND t.absolute_index <= :n"),
    ("phase_snapshot", "t.world_id = :w AND t.absolute_index <= :n"),
    ("phase_snapshot_character", f"t.snapshot_id IN ({_SNAPS})"),
    (
        "user_command",
        "t.id IN (SELECT source_command_id FROM world_event"
        " WHERE world_id = :w AND sequence <= :seq)",
    ),
    ("world_event", "t.world_id = :w AND t.sequence <= :seq"),
    ("event_effect", f"t.event_id IN ({_EVENTS})"),
    ("observation", f"t.world_id = :w AND t.event_id IN ({_EVENTS})"),
    (
        "recent_memory",
        f"t.world_id = :w AND (t.event_id IN ({_EVENTS})"
        " OR (t.event_id IS NULL AND t.created_phase_index <= :n))",
    ),
    ("long_term_memory", "t.world_id = :w AND t.created_phase_index <= :n"),
    ("daily_summary", "t.world_id = :w AND t.day <= :days"),
    ("scene", f"t.world_id = :w AND t.phase_run_id IN ({_RUNS})"),
    ("scene_participant", f"t.scene_id IN ({_SCENES})"),
    ("character_intent", f"t.world_id = :w AND t.snapshot_id IN ({_SNAPS})"),
    ("attempt", f"t.intent_id IN ({_INTENTS})"),
    ("reaction", f"t.attempt_id IN ({_ATTEMPTS})"),
    ("resolution", f"t.scene_id IN ({_SCENES})"),
    (
        "narration",
        f"t.world_id = :w AND (t.scene_id IN ({_SCENES})"
        f" OR (t.scene_id IS NULL AND t.event_id IN ({_EVENTS})))",
    ),
    ("story_initial_setup", _W),
    ("story_prompts", _W),
    ("character_image_prompt", _W),
)

#: Copied with a filter decided in Python (pictures need finished paintings).
EXTRA_TABLES: tuple[tuple[str, str], ...] = (
    ("scene_picture", f"t.world_id = :w AND t.scene_id IN ({_SCENES})"),
    ("image_job", "t.world_id = :w AND t.status = 'ready'"),
    ("asset_record", "t.world_id = :w AND t.status = 'ready'"),
    ("recall_vector", "t.world_id = :w AND t.created_phase_index <= :n"),
    ("story_checkpoint", "t.world_id = :w AND t.absolute_index <= :n"),
)

#: Foreign keys decide this order. user_command and world_event point at
#: each other: commands go in first without their result, then get it back.
INSERT_ORDER: tuple[str, ...] = (
    "world",
    "world_clock",
    "world_config",
    "entity",
    "location",
    "character",
    "character_card_version",
    "character_state",
    "character_intention",
    "travel_route",
    "item_instance",
    "phase_run",
    "phase_snapshot",
    "phase_snapshot_character",
    "user_command",
    "world_event",
    "event_effect",
    "relationship",
    "relationship_evidence",
    "claim",
    "belief",
    "narrative_hook",
    "narrative_arc",
    "activity",
    "scheduled_effect",
    "world_condition",
    "skill_definition",
    "character_skill",
    "training_session",
    "role_grant",
    "focus_assignment",
    "lineage_character",
    "lineage_link",
    "dnd_party_member",
    "dnd_monster",
    "aggregate_version",
    "intervention",
    "intervention_step",
    "macro_period_run",
    "macro_aggregate_effect",
    "macro_interruption",
    "end_condition_evidence",
    "era_summary",
    "observation",
    "recent_memory",
    "long_term_memory",
    "daily_summary",
    "recall_vector",
    "scene",
    "scene_participant",
    "character_intent",
    "attempt",
    "reaction",
    "resolution",
    "narration",
    "asset_record",
    "image_job",
    "scene_picture",
    "story_initial_setup",
    "story_prompts",
    "character_image_prompt",
    "story_checkpoint",
)

#: State rows that history points at (an observation names its observer, a
#: scene its people): a rewind updates these in place and removes only the
#: ones made after the turn. Every other state table is emptied and put back
#: from the checkpoint whole, so a table added to STATE_TABLES is rewound
#: with no change here.
ANCHOR_TABLES: tuple[str, ...] = (
    "world",
    "entity",
    "location",
    "character",
    "character_card_version",
)

#: History rows found through their parent rather than a world_id column.
_HISTORY_SCOPE: dict[str, str] = {
    "phase_snapshot_character": (
        "t.snapshot_id IN (SELECT id FROM phase_snapshot WHERE world_id = :w)"
    ),
    "event_effect": "t.event_id IN (SELECT id FROM world_event WHERE world_id = :w)",
    "scene_participant": "t.scene_id IN (SELECT id FROM scene WHERE world_id = :w)",
}

#: Story setup rather than turns: a rewind leaves these as they are.
_SETUP_TABLES = frozenset({"story_initial_setup", "story_prompts", "character_image_prompt"})

_LATER_EVENTS = "SELECT id FROM world_event WHERE world_id = :w AND sequence > :seq"

#: Columns copied as they are: the stored file a branch shares.
KEEP_AS_IS: frozenset[tuple[str, str]] = frozenset({("asset_record", "content_ref")})

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])")
_STRING_TYPES = frozenset({"character varying", "text", "character"})
_JSON_TYPES = frozenset({"jsonb", "json"})


def completed_days(absolute_index: int) -> int:
    """Days whose day-end work belongs to turns up to this one."""
    return (absolute_index + 1) // PHASES_PER_DAY


def last_day_end(absolute_index: int) -> int:
    """The turn that ended the day before this one's (-1 on day 1); itself at midnight."""
    if absolute_index % PHASES_PER_DAY == PHASES_PER_DAY - 1:
        return absolute_index
    return absolute_index - absolute_index % PHASES_PER_DAY - 1


def _q(table: str) -> str:
    return f'"{table}"'


def _state_sql() -> str:
    """One jsonb document of every changeable row of a story (built in Postgres)."""
    parts = [
        f"'{table}', (SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)"
        f" FROM {_q(table)} t WHERE {where})"
        for table, where in STATE_TABLES
    ]
    config = (
        "'world_config', (SELECT coalesce(jsonb_agg(CASE WHEN length(t.value::text) <= "
        f"{CONFIG_INLINE_CHARS} THEN to_jsonb(t) ELSE jsonb_build_object("
        "'world_id', t.world_id, 'key', t.key, 'value_md5', md5(t.value::text)) END),"
        " '[]'::jsonb) FROM world_config t WHERE t.world_id = :w)"
    )
    parts.append(config)
    # jsonb_build_object takes at most 100 arguments: build it in pieces.
    chunks = [parts[i : i + 20] for i in range(0, len(parts), 20)]
    tables = " || ".join(f"jsonb_build_object({', '.join(chunk)})" for chunk in chunks)
    full = (
        "jsonb_build_object("
        "'observation', (SELECT coalesce(jsonb_object_agg(t.id, t.salience), '{}'::jsonb)"
        " FROM observation t WHERE t.world_id = :w AND t.salience <> 1.0),"
        " 'recent_memory', (SELECT coalesce(jsonb_object_agg(t.id, t.salience), '{}'::jsonb)"
        " FROM recent_memory t WHERE t.world_id = :w AND t.salience <> 1.0))"
    )
    # Salience only moves at day's end (summaries bump what they cite), so
    # a turn inside a day points at the day-end turn before it, when kept:
    # 300 turns of a six-person story kept 63 KB a turn without this.
    salience = (
        "CASE WHEN CAST(:n AS integer) <> CAST(:day_end AS integer)"
        " AND EXISTS (SELECT 1 FROM story_checkpoint c"
        " WHERE c.world_id = :w AND c.absolute_index = CAST(:day_end AS integer)"
        " AND c.state->'salience' ? 'observation')"
        f" THEN jsonb_build_object('at', CAST(:day_end AS integer)) ELSE {full} END"
    )
    return f"jsonb_build_object('tables', {tables}, 'salience', {salience})"


_CAPTURE = text(
    f"""
    INSERT INTO story_checkpoint
        (world_id, absolute_index, event_sequence, schema_version, state, created_at)
    SELECT :w, :n,
           coalesce((SELECT max(sequence) FROM world_event WHERE world_id = :w), 0),
           :schema, {_state_sql()}, now()
    ON CONFLICT (world_id, absolute_index) DO NOTHING
    RETURNING octet_length(state::text)
    """
)


@dataclass(frozen=True)
class _Column:
    type: str
    nullable: bool


@dataclass
class _Schema:
    columns: dict[str, dict[str, _Column]]
    keys: dict[str, tuple[str, ...]]


_schema_cache: _Schema | None = None


class SqlAlchemyCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- checkpoints -------------------------------------------------------

    async def capture(self, world_id: UUID, absolute_index: int) -> int:
        """Keep this turn's state; bytes written (0 when it was already kept)."""
        written = (
            await self._session.execute(
                _CAPTURE,
                {
                    "w": world_id,
                    "n": absolute_index,
                    "schema": CHECKPOINT_SCHEMA_VERSION,
                    "day_end": last_day_end(absolute_index),
                },
            )
        ).scalar_one_or_none()
        return int(written or 0)

    async def prune(self, world_id: UUID, absolute_index: int, recent: int | None = None) -> int:
        """Retention (rewind-001): checkpoints of the newest turns, older day ends.

        Run when turn ``absolute_index`` is kept: every turn at least
        ``recent`` turns older that does not end a day goes. An index range
        delete on the key, so it costs the same at turn 10 and turn 10 000.
        Day-end turns stay, which is also what keeps the salience pointer of
        a turn inside a day valid. Rows deleted.
        """
        window = branches.KEEP_RECENT_TURNS if recent is None else recent
        result = await self._session.execute(
            text(
                "DELETE FROM story_checkpoint WHERE world_id = :w"
                " AND absolute_index <= CAST(:edge AS integer)"
                " AND absolute_index % CAST(:per AS integer) <> CAST(:per AS integer) - 1"
            ),
            {"w": world_id, "edge": absolute_index - window, "per": PHASES_PER_DAY},
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def latest_completed(self, world_id: UUID) -> int | None:
        """The newest turn of the story that finished."""
        found = (
            await self._session.execute(
                text(
                    "SELECT max(absolute_index) FROM phase_run"
                    " WHERE world_id = :w AND state = 'completed'"
                ),
                {"w": world_id},
            )
        ).scalar_one_or_none()
        return None if found is None else int(found)

    async def heads(self, world_id: UUID) -> list[CheckpointHead]:
        rows = (
            await self._session.execute(
                text(
                    "SELECT absolute_index, event_sequence, schema_version FROM story_checkpoint"
                    " WHERE world_id = :w ORDER BY absolute_index"
                ),
                {"w": world_id},
            )
        ).all()
        return [CheckpointHead(int(r[0]), int(r[1]), int(r[2])) for r in rows]

    async def head(self, world_id: UUID, absolute_index: int) -> CheckpointHead | None:
        row = (
            await self._session.execute(
                text(
                    "SELECT absolute_index, event_sequence, schema_version FROM story_checkpoint"
                    " WHERE world_id = :w AND absolute_index = :n"
                ),
                {"w": world_id, "n": absolute_index},
            )
        ).first()
        return None if row is None else CheckpointHead(int(row[0]), int(row[1]), int(row[2]))

    async def state(self, world_id: UUID, absolute_index: int) -> dict[str, Any] | None:
        raw = (
            await self._session.execute(
                text(
                    "SELECT state::text FROM story_checkpoint"
                    " WHERE world_id = :w AND absolute_index = :n"
                ),
                {"w": world_id, "n": absolute_index},
            )
        ).scalar_one_or_none()
        return None if raw is None else cast(dict[str, Any], json.loads(raw))

    async def unnarrated_scenes(self, world_id: UUID, absolute_index: int) -> int:
        """Committed scenes of this turn whose words are not written yet."""
        return int(
            (
                await self._session.execute(
                    text(
                        "SELECT count(*) FROM scene s JOIN phase_run r ON r.id = s.phase_run_id"
                        " WHERE s.world_id = :w AND r.absolute_index = :n"
                        " AND s.event_id IS NOT NULL AND s.narration_status IS NULL"
                    ),
                    {"w": world_id, "n": absolute_index},
                )
            ).scalar_one()
        )

    # --- provenance ----------------------------------------------------------

    async def add_origin(self, origin: StoryBranchOrigin) -> None:
        await self._session.execute(
            text(
                "INSERT INTO story_branch"
                " (world_id, source_world_id, source_index, source_title, created_at)"
                " VALUES (:w, :s, :n, :title, :at)"
            ),
            {
                "w": origin.world_id,
                "s": origin.source_world_id,
                "n": origin.source_index,
                "title": origin.source_title[:128],
                "at": origin.created_at,
            },
        )

    async def origins(self, world_ids: Iterable[UUID]) -> dict[UUID, StoryBranchOrigin]:
        ids = list(world_ids)
        if not ids:
            return {}
        rows = (
            await self._session.execute(
                text(
                    "SELECT b.world_id, b.source_world_id, b.source_index,"
                    " coalesce(c.title, b.source_title), b.created_at"
                    " FROM story_branch b LEFT JOIN story_catalog c"
                    " ON c.world_id = b.source_world_id WHERE b.world_id = ANY(:ids)"
                ),
                {"ids": ids},
            )
        ).all()
        return {
            r[0]: StoryBranchOrigin(
                world_id=r[0],
                source_world_id=r[1],
                source_index=int(r[2]),
                source_title=str(r[3]),
                created_at=cast(datetime, r[4]),
            )
            for r in rows
        }

    # --- the branch copy ------------------------------------------------------

    async def copy_branch(
        self,
        source_id: UUID,
        absolute_index: int,
        head: CheckpointHead,
        state: Mapping[str, Any],
        new_world_id: UUID,
    ) -> BranchCopy:
        """Write a new story equal to ``source_id`` at the end of the turn.

        Changeable state comes from the turn's checkpoint; history up to the
        turn comes from the live tables. Reads the source only.
        """
        if head.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "This turn was kept in an older format and can't be branched.",
            )
        schema = await self._schema()
        params = {
            "w": source_id,
            "n": absolute_index,
            "seq": head.event_sequence,
            "days": completed_days(absolute_index),
        }
        tables: dict[str, list[Row]] = {
            table: [dict(r) for r in rows]
            for table, rows in cast(Mapping[str, list[Row]], state["tables"]).items()
        }
        tables["world_config"] = await self._resolve_config(source_id, tables["world_config"])
        for table, where in HISTORY_TABLES:
            tables[table] = await self._rows(table, where, params)
        extras = {table: await self._rows(table, where, params) for table, where in EXTRA_TABLES}

        salience = await self._salience(
            source_id, cast(Mapping[str, Any], state.get("salience", {}))
        )
        for table in ("observation", "recent_memory"):
            bumped = salience.get(table, {})
            for row in tables[table]:
                row["salience"] = float(bumped.get(str(row["id"]), 1.0))

        copied: set[str] = {str(source_id)}
        for table, rows in tables.items():
            copied |= _key_ids(schema, table, rows)

        # Pictures need a finished painting; their jobs and assets come along.
        jobs_by_id = {str(r["id"]): r for r in extras["image_job"]}
        pictures = [
            r
            for r in extras["scene_picture"]
            if str(r["scene_id"]) in copied and str(r["job_id"]) in jobs_by_id
        ]
        picture_ids = {str(r["id"]) for r in pictures}
        subjects = copied | picture_ids
        assets = [
            r
            for r in extras["asset_record"]
            if r.get("subject_id") is None or str(r["subject_id"]) in subjects
        ]
        asset_ids = {str(r["id"]) for r in assets}
        jobs = [
            r
            for r in extras["image_job"]
            if (r.get("subject_id") is None or str(r["subject_id"]) in subjects)
            and (r.get("result_asset_id") is None or str(r["result_asset_id"]) in asset_ids)
        ]
        job_ids = {str(r["id"]) for r in jobs}
        pictures = [r for r in pictures if str(r["job_id"]) in job_ids]
        for row in pictures:
            if row.get("repaint_job_id") is not None and str(row["repaint_job_id"]) not in job_ids:
                row["repaint_job_id"] = None
        tables["scene_picture"] = pictures
        tables["image_job"] = jobs
        tables["asset_record"] = assets
        for table in ("scene_picture", "image_job", "asset_record"):
            copied |= _key_ids(schema, table, tables[table])

        known = await self._source_ids(source_id) | copied
        checkpoints = extras["story_checkpoint"]
        for checkpoint in checkpoints:
            known |= _state_key_ids(schema, checkpoint["state"])

        remap = _derived_ids(source_id, new_world_id, tables)
        for table, rows in tables.items():
            for row in rows:
                for column in schema.keys.get(table, ()):
                    value = row.get(column)
                    if isinstance(value, str) and schema.columns[table][column].type == "uuid":
                        remap.setdefault(value, str(uuid4()))
        tables["recall_vector"] = [
            r for r in extras["recall_vector"] if _names_copied(r["source_id"], copied)
        ]

        rename = _Renamer(schema, remap, copied, known)
        out: dict[str, list[Row]] = {
            table: [rename.row(table, row) for row in rows] for table, rows in tables.items()
        }
        for row in out["phase_snapshot"]:
            digest = hashlib.sha256(f"{row['content_hash']}:{new_world_id.hex}".encode())
            row["content_hash"] = digest.hexdigest()
        results = {str(r["id"]): r.get("result_event_id") for r in out["user_command"]}
        for row in out["user_command"]:
            row["result_event_id"] = None

        written = 0
        for table in INSERT_ORDER:
            if table == "story_checkpoint":
                continue
            written += await self._insert(schema, table, out.get(table, []))
        await self._session.execute(
            text(
                "UPDATE user_command c SET result_event_id = r.result_event_id"
                " FROM jsonb_to_recordset(CAST(:rows AS jsonb))"
                " AS r(id uuid, result_event_id uuid) WHERE c.id = r.id"
            ),
            {
                "rows": json.dumps(
                    [{"id": k, "result_event_id": v} for k, v in results.items() if v]
                )
            },
        )
        fingerprints = await self._config_fingerprints(source_id, new_world_id, rename)
        kept = [
            rename.checkpoint(checkpoint, new_world_id, fingerprints) for checkpoint in checkpoints
        ]
        written += await self._insert(schema, "story_checkpoint", kept)
        return BranchCopy(world_id=new_world_id, remap=remap, rows=written)

    # --- rewind in place --------------------------------------------------------

    async def rewind(
        self,
        world_id: UUID,
        absolute_index: int,
        head: CheckpointHead,
        state: Mapping[str, Any],
    ) -> dict[str, int]:
        """Put the story back as it stood at the end of the turn (rewind-001).

        Changeable state comes back from the turn's checkpoint; history after
        the turn goes (the same "up to the turn" rule a branch copies by),
        with what hangs off it: pictures of removed scenes and their jobs and
        asset rows, model calls of removed turns, recall vectors, later
        checkpoints and task runs. Stored picture files are left on disk
        (branches share them by ``content_ref``). The caller's transaction
        makes it all or nothing. Rows removed or restored, per table.
        """
        if head.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "This turn was kept in an older format, so the story can't go back to it.",
            )
        schema = await self._schema()
        params: dict[str, Any] = {
            "w": world_id,
            "n": absolute_index,
            "seq": head.event_sequence,
            "days": completed_days(absolute_index),
        }
        tables: dict[str, list[Row]] = {
            table: [dict(r) for r in rows]
            for table, rows in cast(Mapping[str, list[Row]], state["tables"]).items()
        }
        # Checked before anything changes: both refuse rather than guess.
        tables["world_config"] = await self._resolve_config(world_id, tables["world_config"])
        salience = await self._salience(
            world_id, cast(Mapping[str, Any], state.get("salience", {}))
        )
        before = await self._source_ids(world_id)
        counts: dict[str, int] = {}

        async def run(label: str, sql: str, **extra: Any) -> None:
            merged = {**params, **extra}
            used = {k: v for k, v in merged.items() if f":{k}" in sql}
            result = await self._session.execute(text(sql), used)
            counts[label] = counts.get(label, 0) + int(getattr(result, "rowcount", 0) or 0)

        later_runs = [
            r[0]
            for r in (
                await self._session.execute(
                    text("SELECT id FROM phase_run WHERE world_id = :w AND absolute_index > :n"),
                    {"w": world_id, "n": absolute_index},
                )
            ).all()
        ]
        call_tasks = [
            str(r[0])
            for r in (
                await self._session.execute(
                    text(
                        "SELECT DISTINCT task_run_id FROM model_call WHERE world_id = :w"
                        " AND phase_run_id = ANY(:runs) AND task_run_id IS NOT NULL"
                    ),
                    {"w": world_id, "runs": later_runs},
                )
            ).all()
        ]

        # 1. Commands let go of the events that are about to go.
        await run(
            "user_command.result",
            "UPDATE user_command SET result_event_id = NULL WHERE world_id = :w"
            f" AND result_event_id IN ({_LATER_EVENTS})",
        )
        # 2. State other than the anchors goes whole; the checkpoint puts it back.
        state_where = dict(STATE_TABLES)
        for table in reversed(INSERT_ORDER):
            if table in ANCHOR_TABLES:
                continue
            if table == "world_config":
                await run(table, "DELETE FROM world_config WHERE world_id = :w")
            elif table in state_where:
                await run(table, f"DELETE FROM {_q(table)} t WHERE {state_where[table]}")
        # 3. What hangs off removed turns.
        await run(
            "scene_picture",
            "DELETE FROM scene_picture t WHERE t.world_id = :w"
            f" AND NOT coalesce(t.scene_id IN ({_SCENES}), false)",
        )
        # Model calls of removed turns stay, with their cost and manifest: the
        # money was spent, and the story's spend must not drop on a rewind.
        # Only their links to the removed run and task go (a replayed turn
        # derives the same run and task ids).
        await run(
            "model_call",
            "UPDATE model_call SET phase_run_id = NULL, task_run_id = NULL"
            " WHERE world_id = :w AND phase_run_id = ANY(:runs)",
            runs=later_runs,
        )
        await run(
            "outbox_message",
            f"DELETE FROM outbox_message WHERE world_id = :w AND event_id IN ({_LATER_EVENTS})",
        )
        await run(
            "story_checkpoint",
            "DELETE FROM story_checkpoint WHERE world_id = :w AND absolute_index > :n",
        )
        # 4. History after the turn, children first.
        # Snapshots are immutable but for this (migration 0060), this transaction only.
        await self._session.execute(text("SELECT set_config('worldsim.rewind', 'on', true)"))
        history_where = dict(HISTORY_TABLES)
        for table in reversed(INSERT_ORDER):
            if table not in history_where or table in _SETUP_TABLES:
                continue
            if table == "user_command":
                # Kept: the commands the kept events came from (as a branch).
                await run(
                    table,
                    "DELETE FROM user_command t WHERE t.world_id = :w AND t.id NOT IN"
                    " (SELECT source_command_id FROM world_event WHERE world_id = :w"
                    " AND source_command_id IS NOT NULL)",
                )
                continue
            scope = _HISTORY_SCOPE.get(table, "t.world_id = :w")
            await run(
                table,
                f"DELETE FROM {_q(table)} t WHERE {scope}"
                f" AND NOT coalesce(({history_where[table]}), false)",
            )
        await self._session.execute(text("SELECT set_config('worldsim.rewind', 'off', true)"))
        # 5. Anchors: back to their values at the turn; later ones go.
        for table in ANCHOR_TABLES:
            counts[f"{table}.restored"] = await self._upsert(schema, table, tables.get(table, []))
        for table in reversed(ANCHOR_TABLES[1:]):
            keys = schema.keys.get(table, ())
            if len(keys) != 1:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED, f"rewind: {table} needs a one-column key"
                )
            kept_ids = [str(row[keys[0]]) for row in tables.get(table, [])]
            await run(
                table,
                f"DELETE FROM {_q(table)} t WHERE {state_where[table]}"
                f' AND NOT (t."{keys[0]}"::text = ANY(CAST(:kept AS text[])))',
                kept=kept_ids,
            )
        # 6. The rest of the state, as it stood.
        for table in INSERT_ORDER:
            if table in ANCHOR_TABLES or (table not in state_where and table != "world_config"):
                continue
            counts[f"{table}.restored"] = await self._insert(schema, table, tables.get(table, []))
        for table in ("observation", "recent_memory"):
            await run(
                f"{table}.salience",
                f"UPDATE {table} t SET salience = coalesce("
                "(CAST(:bumped AS jsonb) ->> t.id::text)::double precision, 1.0)"
                " WHERE t.world_id = :w",
                bumped=json.dumps(salience.get(table, {})),
            )
        # 7. Pictures, jobs and recall of rows that no longer exist.
        gone = sorted(before - await self._source_ids(world_id))
        await run(
            "image_job",
            "DELETE FROM image_job WHERE world_id = :w AND (subject_id::text = ANY(CAST(:gone"
            " AS text[])) OR result_asset_id IN (SELECT id FROM asset_record WHERE world_id = :w"
            " AND subject_id::text = ANY(CAST(:gone AS text[]))))",
            gone=gone,
        )
        await run(
            "asset_record",
            "DELETE FROM asset_record WHERE world_id = :w"
            " AND subject_id::text = ANY(CAST(:gone AS text[]))",
            gone=gone,
        )
        gone_set = set(gone)
        vectors = [
            str(r[0])
            for r in (
                await self._session.execute(
                    text("SELECT source_id FROM recall_vector WHERE world_id = :w"),
                    {"w": world_id},
                )
            ).all()
        ]
        stale = [v for v in vectors if _names_copied(v, gone_set)]
        await run(
            "recall_vector",
            "DELETE FROM recall_vector WHERE world_id = :w AND (created_phase_index > :n"
            " OR source_id = ANY(CAST(:stale AS text[])))",
            stale=stale,
        )
        # 8. Task runs of removed turns (a slot held right now stays).
        await run(
            "task_run",
            "DELETE FROM task_run t WHERE t.world_id = :w AND t.state <> 'running'"
            " AND (t.id::text = ANY(CAST(:tasks AS text[]))"
            " OR (t.idempotency_key LIKE :slots"
            " AND split_part(t.idempotency_key, ':', 4) ~ '^[0-9]+$'"
            " AND split_part(t.idempotency_key, ':', 4)::integer > :n))"
            " AND t.id NOT IN (SELECT source_task_id FROM world_event"
            " WHERE world_id = :w AND source_task_id IS NOT NULL)",
            tasks=call_tasks,
            slots=f"execute:{world_id.hex}:phase:%",
        )
        return counts

    async def _upsert(self, schema: _Schema, table: str, rows: list[Row]) -> int:
        """Insert rows, or set every column of the row with that key."""
        if not rows:
            return 0
        present = schema.columns[table]
        keys = schema.keys[table]
        names = sorted({key for row in rows for key in row} & present.keys())
        columns = ", ".join(f'"{name}"' for name in names)
        updates = ", ".join(f'"{n}" = EXCLUDED."{n}"' for n in names if n not in keys)
        conflict = ", ".join(f'"{k}"' for k in keys)
        action = f"DO UPDATE SET {updates}" if updates else "DO NOTHING"
        await self._session.execute(
            text(
                f"INSERT INTO {_q(table)} ({columns}) SELECT {columns}"
                f" FROM jsonb_populate_recordset(NULL::{_q(table)}, CAST(:rows AS jsonb))"
                f" ON CONFLICT ({conflict}) {action}"
            ),
            {"rows": json.dumps(rows)},
        )
        return len(rows)

    # --- helpers ---------------------------------------------------------------

    async def _rows(self, table: str, where: str, params: Mapping[str, Any]) -> list[Row]:
        raw = (
            await self._session.execute(
                text(
                    f"SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)::text"
                    f" FROM {_q(table)} t WHERE {where}"
                ),
                {k: v for k, v in params.items() if f":{k}" in where},
            )
        ).scalar_one()
        return cast(list[Row], json.loads(raw))

    async def _salience(
        self, source_id: UUID, kept: Mapping[str, Any]
    ) -> Mapping[str, Mapping[str, float]]:
        """The turn's salience: kept with it, or with the day-end turn before it."""
        if "at" not in kept:
            return cast(Mapping[str, Mapping[str, float]], kept)
        earlier = await self.state(source_id, int(kept["at"]))
        found = cast(Mapping[str, Any], (earlier or {}).get("salience", {}))
        if earlier is None or "at" in found:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "Part of this turn's state was not kept, so it can't be branched exactly.",
            )
        return cast(Mapping[str, Mapping[str, float]], found)

    async def _resolve_config(self, source_id: UUID, rows: list[Row]) -> list[Row]:
        """Config rows kept as a fingerprint take the live value, if unchanged."""
        if not any("value_md5" in row for row in rows):
            return rows
        live = {
            str(r[0]): (str(r[1]), str(r[2]))
            for r in (
                await self._session.execute(
                    text(
                        "SELECT key, md5(value::text), value::text FROM world_config"
                        " WHERE world_id = :w"
                    ),
                    {"w": source_id},
                )
            ).all()
        }
        out: list[Row] = []
        for row in rows:
            if "value_md5" not in row:
                out.append(row)
                continue
            current = live.get(str(row["key"]))
            if current is None or current[0] != row["value_md5"]:
                raise DomainError(
                    ErrorCode.PRECONDITION_FAILED,
                    "The story's setup changed after this turn, so it can't be branched exactly.",
                )
            value = json.loads(current[1])
            out.append({"world_id": row["world_id"], "key": row["key"], "value": value})
        return out

    async def _config_fingerprints(
        self, source_id: UUID, new_world_id: UUID, rename: _Renamer
    ) -> dict[str, tuple[str, str]]:
        """key -> (source fingerprint, branch fingerprint) of each config value."""
        rows = (
            await self._session.execute(
                text(
                    "SELECT s.key, md5(s.value::text), md5(b.value::text) FROM world_config s"
                    " JOIN world_config b ON b.key = s.key AND b.world_id = :b"
                    " WHERE s.world_id = :w"
                ),
                {"w": source_id, "b": new_world_id},
            )
        ).all()
        return {str(r[0]): (str(r[1]), str(r[2])) for r in rows}

    async def _source_ids(self, source_id: UUID) -> set[str]:
        """Every row id of the source story, whether or not it is copied."""
        schema = await self._schema()
        selects = [
            f"SELECT t.id::text FROM {_q(table)} t WHERE t.world_id = :w"
            for table, columns in sorted(schema.columns.items())
            if columns.get("id", _Column("", True)).type == "uuid"
            and columns.get("world_id", _Column("", True)).type == "uuid"
        ]
        selects.append(
            'SELECT t.id::text FROM character_card_version t JOIN "character" c'
            " ON c.id = t.character_id WHERE c.world_id = :w"
        )
        selects.append(
            "SELECT t.id::text FROM intervention_step t JOIN intervention i"
            " ON i.id = t.intervention_id WHERE i.world_id = :w"
        )
        rows = (await self._session.execute(text(" UNION ".join(selects)), {"w": source_id})).all()
        return {str(r[0]) for r in rows} | {str(source_id)}

    async def _insert(self, schema: _Schema, table: str, rows: list[Row]) -> int:
        if not rows:
            return 0
        present = schema.columns[table]
        names = sorted({key for row in rows for key in row} & present.keys())
        columns = ", ".join(f'"{name}"' for name in names)
        await self._session.execute(
            text(
                f"INSERT INTO {_q(table)} ({columns}) SELECT {columns}"
                f" FROM jsonb_populate_recordset(NULL::{_q(table)}, CAST(:rows AS jsonb))"
            ),
            {"rows": json.dumps(rows)},
        )
        return len(rows)

    async def _schema(self) -> _Schema:
        global _schema_cache
        if _schema_cache is not None:
            return _schema_cache
        columns: dict[str, dict[str, _Column]] = {}
        for found in (
            await self._session.execute(
                text(
                    "SELECT table_name, column_name, data_type, is_nullable = 'YES'"
                    " FROM information_schema.columns WHERE table_schema = current_schema()"
                )
            )
        ).all():
            columns.setdefault(str(found[0]), {})[str(found[1])] = _Column(
                str(found[2]), bool(found[3])
            )
        keys: dict[str, list[str]] = {}
        for found in (
            await self._session.execute(
                text(
                    "SELECT tc.table_name, kcu.column_name"
                    " FROM information_schema.table_constraints tc"
                    " JOIN information_schema.key_column_usage kcu"
                    " ON kcu.constraint_name = tc.constraint_name"
                    " AND kcu.table_schema = tc.table_schema"
                    " WHERE tc.constraint_type = 'PRIMARY KEY'"
                    " AND tc.table_schema = current_schema()"
                    " ORDER BY kcu.ordinal_position"
                )
            )
        ).all():
            keys.setdefault(str(found[0]), []).append(str(found[1]))
        _schema_cache = _Schema(columns, {t: tuple(c) for t, c in keys.items()})
        return _schema_cache


def _key_ids(schema: _Schema, table: str, rows: Iterable[Row]) -> set[str]:
    columns = schema.columns.get(table, {})
    found: set[str] = set()
    for column in schema.keys.get(table, ()):
        if columns.get(column, _Column("", True)).type != "uuid":
            continue
        found |= {str(row[column]) for row in rows if row.get(column) is not None}
    return found


def _state_key_ids(schema: _Schema, state: Any) -> set[str]:
    """Key ids of every row kept in a checkpoint (some no longer exist)."""
    found: set[str] = set()
    document = cast(Mapping[str, Any], state or {})
    tables = cast(Mapping[str, list[Row]], document.get("tables", {}))
    for table, rows in tables.items():
        found |= _key_ids(schema, table, rows)
    return found


def _names_copied(source_id: str, copied: set[str]) -> bool:
    """recall_vector ids read ``obs:<uuid>:<key>`` or ``mem:<uuid>``."""
    return any(match.group(0).lower() in copied for match in _UUID.finditer(source_id))


def _derived_ids(
    source_id: UUID, new_world_id: UUID, tables: Mapping[str, list[Row]]
) -> dict[str, str]:
    """Ids the engine derives rather than draws keep their derivation."""
    from worldsim.application.orchestration.service import derive_run_id, derive_snapshot_id

    remap: dict[str, str] = {str(source_id): str(new_world_id)}
    run_index: dict[str, int] = {}
    for row in tables["phase_run"]:
        run = derive_run_id(new_world_id, int(row["absolute_index"]))
        remap[str(row["id"])] = str(run)
        run_index[str(row["id"])] = int(row["absolute_index"])
    for row in tables["phase_snapshot"]:
        old_run = str(row["phase_run_id"])
        if old_run in remap:
            remap[str(row["id"])] = str(derive_snapshot_id(UUID(remap[old_run])))
    for row in tables["character"]:
        remap.setdefault(str(row["id"]), str(uuid4()))
    for row in tables["scene"]:
        remap.setdefault(str(row["id"]), str(uuid4()))

    def mapped(value: Any) -> UUID | None:
        found = remap.get(str(value))
        return UUID(found) if found is not None else None

    for row in tables["character_intent"]:
        snapshot, author = mapped(row["snapshot_id"]), mapped(row["author_character_id"])
        if snapshot is not None and author is not None:
            remap[str(row["id"])] = str(derive_intent_id(new_world_id, snapshot, author))
    for row in tables["attempt"]:
        intent = mapped(row["intent_id"])
        if intent is not None:
            remap[str(row["id"])] = str(derive_attempt_id(intent))
    for row in tables["reaction"]:
        attempt, reactor = mapped(row["attempt_id"]), mapped(row["reactor_character_id"])
        if attempt is not None and reactor is not None:
            remap[str(row["id"])] = str(derive_reaction_id(attempt, reactor))
    for row in tables["resolution"]:
        scene = mapped(row["scene_id"])
        if scene is not None:
            remap[str(row["id"])] = str(derive_resolution_id(scene))
    return remap


class _Renamer:
    """Applies the renaming rule (module docstring) to rows and documents."""

    def __init__(
        self, schema: _Schema, remap: dict[str, str], copied: set[str], known: set[str]
    ) -> None:
        self._schema = schema
        self._remap = remap
        self._copied = copied
        self._known = known

    def _id(self, value: str) -> str | None:
        """A renamed id, a fresh stand-in for a source id not copied, or None."""
        lowered = value.lower()
        if lowered in self._remap:
            return self._remap[lowered]
        if lowered in self._known:
            return self._remap.setdefault(lowered, str(uuid4()))
        return None

    def text(self, value: str) -> str:
        def hyphen(match: re.Match[str]) -> str:
            found = self._id(match.group(0))
            return found if found is not None else match.group(0)

        def bare(match: re.Match[str]) -> str:
            found = self._id(str(UUID(match.group(0))))
            return UUID(found).hex if found is not None else match.group(0)

        return _HEX.sub(bare, _UUID.sub(hyphen, value))

    def json(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.json(item) for item in cast(list[Any], value)]
        if isinstance(value, dict):
            return {self.text(str(k)): self.json(v) for k, v in cast(dict[str, Any], value).items()}
        return value

    def row(self, table: str, row: Row) -> Row:
        columns = self._schema.columns.get(table, {})
        keys = self._schema.keys.get(table, ())
        out: Row = {}
        for name, value in row.items():
            column = columns.get(name)
            if column is None or value is None or (table, name) in KEEP_AS_IS:
                out[name] = value
            elif column.type == "uuid":
                out[name] = self._column_id(table, name, str(value), column, name in keys)
            elif column.type in _JSON_TYPES or column.type == "ARRAY":
                out[name] = self.json(value)
            elif column.type in _STRING_TYPES:
                out[name] = self.text(str(value))
            else:
                out[name] = value
        return out

    def _column_id(
        self, table: str, name: str, value: str, column: _Column, key: bool
    ) -> str | None:
        lowered = value.lower()
        if key or lowered in self._copied:
            return self._remap[lowered]
        if lowered in self._known:
            if not column.nullable:
                raise DomainError(
                    ErrorCode.INVARIANT_VIOLATED,
                    f"branch copy: {table}.{name} points at a row that is not copied",
                )
            return None
        return value

    def checkpoint(
        self, row: Row, new_world_id: UUID, fingerprints: Mapping[str, tuple[str, str]]
    ) -> Row:
        out = self.row("story_checkpoint", row)
        out["world_id"] = str(new_world_id)
        state = cast(dict[str, Any], out["state"])
        config = cast(list[Row], state.get("tables", {}).get("world_config", []))
        for entry in config:
            if "value_md5" not in entry:
                continue
            pair = fingerprints.get(str(entry["key"]))
            # A value that changed since that turn stays unmatched: that
            # turn of the branch is then refused, as it is in the source.
            entry["value_md5"] = pair[1] if pair and pair[0] == entry["value_md5"] else "changed"
        return out
