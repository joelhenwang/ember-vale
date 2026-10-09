"""Beat-engine overhead benchmark: everything in a beat that is not model wait.

Seeds a ring of places and a cast in a throwaway database
(``embervale_bench2`` on the dev server, dropped and re-created each run,
never the dev data), then runs beats through the real Stage1Orchestrator
with scripted fake gateways that answer instantly. Characters talk, move,
observe and wait in a fixed rotation, so scenes, reactions, resolution,
narration, the director and day-end summaries all run. No network, no
spend.

Per beat it records the orchestrator's own phase timings, the SQL
statement count and SQL time (SQLAlchemy cursor events), and wall time.
Optionally profiles a window of beats with cProfile.

    python scripts/beat_bench.py --cast 3 --beats 100 [--places 6]
        [--checkpoints 10,100] [--profile 90:100] [--json out.json]
        [--verify-reads] [--bystanders 2] [--cite 0.3] [--salient-cap N]
        [--keep-turns N]

``--keep-turns`` overrides how many newest turns keep their checkpoint
(retention, rewind-001; default 200); the result reports what is stored.

``--verify-reads`` builds every decision and reaction context a second time
from fresh reads and stops on any byte of difference (phase_reads.VERIFY).

Reads WORLDSIM_DATABASE__URL (export that single variable; never source .env).
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import io
import json
import os
import pstats
import re
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

BACKEND = Path(__file__).resolve().parents[1]
BENCH_DB = os.environ.get("BEAT_BENCH_DB", "embervale_bench2")

#: A pool of names large enough for the biggest cast.
NAMES = [
    "Wren", "Ash", "Marg", "Tamsin", "Corin", "Isolde", "Bram", "Fenna", "Odo", "Lysa",
    "Pell", "Rook", "Sable", "Teodor", "Ulla", "Vesna", "Wick", "Yara", "Zeph", "Aldo",
    "Brisa", "Cael", "Dunya", "Edda", "Faro", "Gisla", "Hobb", "Ivo", "Jessamy", "Kell",
]  # fmt: skip


# --- database -----------------------------------------------------------------


def fresh_database() -> None:
    """Drop and re-create the bench database, migrate it, point the process at it."""
    from alembic import command
    from alembic.config import Config
    from psycopg import connect

    from worldsim.infrastructure.db.urls import to_sync_url

    base = os.environ["WORLDSIM_DATABASE__URL"]
    admin = re.sub(r"/[^/]+$", "/postgres", to_sync_url(base))
    with connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {BENCH_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {BENCH_DB}")
    os.environ["WORLDSIM_DATABASE__URL"] = re.sub(r"/[^/]+$", f"/{BENCH_DB}", base)
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")


# --- world --------------------------------------------------------------------


@dataclass
class Seeded:
    world: UUID
    people: dict[str, UUID]
    places: dict[str, UUID]
    home: dict[str, str]


async def seed(engine: Any, cast: int, places: int) -> Seeded:
    from worldsim.domain.characters import Character, CharacterCard
    from worldsim.domain.ids import new_card_id, new_character_id, new_location_id, new_world_id
    from worldsim.domain.world import Location, Route, World
    from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work

    place_names = [f"Place {chr(65 + i)}" for i in range(places)]
    place_ids = {name: new_location_id() for name in place_names}
    people: dict[str, UUID] = {}
    home: dict[str, str] = {}
    async with create_unit_of_work(engine) as uow:
        world = new_world_id()
        await uow.worlds.add(World(id=world, name="Bench Vale", seed_version="beat-bench"))
        for i, name in enumerate(place_names):
            # a ring: each place links to its two neighbours, one beat apart
            neighbours = {place_names[(i - 1) % places], place_names[(i + 1) % places]}
            routes = [
                Route(
                    id=uuid4(),
                    destination_location_id=place_ids[n],
                    duration_phases=1,
                    stamina_cost=2,
                )
                for n in sorted(neighbours)
                if n != name
            ]
            await uow.locations.add(
                Location(id=place_ids[name], world_id=world, name=name, routes=routes)
            )
        for i in range(cast):
            name = NAMES[i]
            cid = new_character_id()
            people[name] = cid
            # pairs share a place, so there is someone to talk to
            where = place_names[(i // 2) % places]
            home[name] = where
            await uow.characters.add_identity(cid, world, name)
            await uow.characters.add_card(
                CharacterCard(
                    id=new_card_id(),
                    character_id=cid,
                    name=name,
                    personality=f"{name} is curious and talkative.",
                    version=1,
                )
            )
            await uow.characters.add_state(
                Character(
                    id=cid,
                    world_id=world,
                    name=name,
                    card_version=1,
                    location_id=place_ids[where],
                    stamina=100,
                    mana=40,
                )
            )
            await uow.versions.ensure(cid, world, "character")
        await uow.versions.ensure(world, world, "world")
        await uow.commit()
    return Seeded(world, people, place_ids, home)


# --- scripted model -----------------------------------------------------------


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass
class Script:
    """Answers each role from the prompt alone, deterministically."""

    seeded: Seeded
    calls: dict[str, int] = field(default_factory=dict)
    dump: Path | None = None
    #: Share of a day's sources the day-end summary cites. Cited sources gain
    #: salience, as in live play; 0 cites nothing (the old behaviour).
    cite: float = 0.0

    def _note(self, role: str, prompt: str) -> int:
        n = self.calls.get(role, 0) + 1
        self.calls[role] = n
        if self.dump is not None and n <= 3:
            (self.dump / f"{role}-{n}.txt").write_text(prompt, encoding="utf-8")
        return n

    def _actor(self, prompt: str) -> tuple[str, UUID] | None:
        # the decision prompt names the actor first ("You are X" or "X," …)
        best: tuple[int, str] | None = None
        for name in self.seeded.people:
            at = prompt.find(name)
            if at >= 0 and (best is None or at < best[0]):
                best = (at, name)
        if best is None:
            return None
        return best[1], self.seeded.people[best[1]]

    def character(self, prompt: str) -> str:
        n = self._note("character", prompt)
        found = self._actor(prompt)
        if found is None:
            return json.dumps({"family": "wait"})
        name, me = found
        ids = set(_UUID.findall(prompt))
        others = [
            (other, cid)
            for other, cid in self.seeded.people.items()
            if cid != me and str(cid) in ids
        ]
        places = [pid for pid in self.seeded.places.values() if str(pid) in ids]
        turn = (n + len(name)) % 5
        if turn in (0, 1) and others:
            other, cid = others[n % len(others)]
            return json.dumps(
                {
                    "family": "communicate",
                    "target_character_id": str(cid),
                    "topic": f"asks {other} about the road and the weather, turn {n}",
                }
            )
        if turn == 2 and places:
            return json.dumps(
                {"family": "move", "destination_location_id": str(places[n % len(places)])}
            )
        if turn == 3:
            return json.dumps({"family": "observe", "focus": "the square"})
        return json.dumps({"family": "wait"})

    def reaction(self, prompt: str) -> str:
        n = self._note("reaction", prompt)
        found = self._actor(prompt)
        if found is not None and n % 2 == 0:
            ids = set(_UUID.findall(prompt))
            others = [
                cid for cid in self.seeded.people.values() if cid != found[1] and str(cid) in ids
            ]
            if others:
                return json.dumps(
                    {
                        "family": "communicate",
                        "target_character_id": str(others[0]),
                        "topic": f"answers kindly, reply {n}",
                    }
                )
        return json.dumps({"family": "observe", "focus": "the speaker"})

    def resolver(self, prompt: str) -> str:
        self._note("resolver", prompt)
        return json.dumps({"outcome": "success", "effects": [], "rationale": "It goes as tried."})

    def narrator(self, prompt: str) -> str:
        self._note("narrator", prompt)
        keys = re.findall(r'key "([^"]+)"', prompt)[:2] or ["place"]
        return json.dumps(
            [
                {"text": "The square hums with talk as the light shifts.", "cited_fact_keys": keys},
                {"text": "Someone laughs; the road waits beyond.", "cited_fact_keys": keys[:1]},
            ]
        )

    def director(self, prompt: str) -> str:
        self._note("director", prompt)
        return json.dumps({"kind": "noop", "reason": "the story is moving"})

    def summary(self, prompt: str) -> str:
        self._note("summary", prompt)
        if self.cite <= 0:
            return json.dumps({"summary": "A day of talk and short walks.", "highlights": []})
        tags = list(dict.fromkeys(re.findall(r"^\[([om]\d+)\]", prompt, re.MULTILINE)))
        cited = [t for i, t in enumerate(tags) if (i * self.cite) % 1 + self.cite >= 1]
        return json.dumps({"text": "A day of talk and short walks.", "source_ids": cited})


def gateways(script: Script) -> tuple[Callable[[str], Any], dict[str, Any]]:
    from worldsim.application.ports.model_gateway import CompletionRequest
    from worldsim.infrastructure.model_gateway.fake import FakeGateway
    from worldsim.infrastructure.model_gateway.selection import FAKE_PROFILES

    answer: dict[str, Callable[[str], str]] = {
        "character": script.character,
        "reaction": script.reaction,
        "resolver": script.resolver,
        "narrator": script.narrator,
        "director": script.director,
        "summary": script.summary,
    }
    built: dict[str, FakeGateway] = {}
    for role, profile in FAKE_PROFILES.items():

        def route(request: CompletionRequest, _role: str = role) -> str:
            return answer[_role](request.prompt)

        built[role] = FakeGateway(profile=profile, route=route)
    return (lambda role: built[role]), dict(FAKE_PROFILES)


# --- SQL counting ---------------------------------------------------------------


@dataclass
class SqlMeter:
    count: int = 0
    seconds: float = 0.0
    checkouts: int = 0
    by_table: dict[str, int] = field(default_factory=dict)
    #: statement shape (literals and parameter lists folded) -> count
    by_shape: dict[str, int] = field(default_factory=dict)
    _started: dict[int, float] = field(default_factory=dict)

    def install(self, engine: Any) -> None:
        from sqlalchemy import event

        sync = engine.sync_engine

        @event.listens_for(sync.pool, "checkout")
        def _checkout(*_: Any) -> None:
            self.checkouts += 1

        @event.listens_for(sync, "before_cursor_execute")
        def _before(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
            self._started[id(cursor)] = time.perf_counter()

        @event.listens_for(sync, "after_cursor_execute")
        def _after(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
            started = self._started.pop(id(cursor), None)
            if started is not None:
                self.seconds += time.perf_counter() - started
            self.count += 1
            m = re.search(r"\b(?:FROM|INTO|UPDATE)\s+(\w+)", statement, re.I)
            key = m.group(1) if m else statement.split(None, 1)[0]
            self.by_table[key] = self.by_table.get(key, 0) + 1
            shape = re.sub(r"\$\d+(?:::\w+(?:\[\])?)?", "?", " ".join(statement.split()))
            shape = re.sub(r"\((?:\?,\s*)+\?\)", "(?…)", shape)[:220]
            self.by_shape[shape] = self.by_shape.get(shape, 0) + 1

    def snapshot(self) -> tuple[int, float]:
        return self.count, self.seconds


# --- run ----------------------------------------------------------------------


async def run(args: argparse.Namespace) -> dict[str, Any]:
    from worldsim.application.orchestration.stage1 import Stage1Orchestrator
    from worldsim.application.tasks.service import TaskService
    from worldsim.application.tracing.service import TraceService
    from worldsim.application.transactions.canonical import CanonicalTransaction
    from worldsim.infrastructure.db.engine import create_engine
    from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
    from worldsim.infrastructure.settings import Settings
    from worldsim.infrastructure.tracing.langsmith import NullExporter

    engine = create_engine(Settings())
    meter = SqlMeter()
    meter.install(engine)
    seeded = await seed(engine, args.cast, args.places)
    dump = Path(args.dump) if args.dump else None
    if dump is not None:
        dump.mkdir(parents=True, exist_ok=True)
    script = Script(seeded, dump=dump, cite=args.cite)
    gateway_for, profiles = gateways(script)

    def factory() -> Any:
        return create_unit_of_work(engine)

    orchestrator = Stage1Orchestrator(
        factory,
        CanonicalTransaction(factory),
        TaskService(factory),
        TraceService(factory, NullExporter()),
        gateway_for,
        profiles,
        reacting_bystanders=None if args.bystanders < 0 else args.bystanders,
    )
    checkpoints = {int(c) for c in args.checkpoints.split(",") if c} if args.checkpoints else set()
    prof_from, prof_to = (0, -1)
    if args.profile:
        a, b = args.profile.split(":")
        prof_from, prof_to = int(a), int(b)
    profiler = cProfile.Profile() if args.profile else None

    beats: list[dict[str, Any]] = []
    for index in range(1, args.beats + 1):
        q0, s0 = meter.snapshot()
        c0 = meter.checkouts
        shapes_before = dict(meter.by_shape) if index in checkpoints else None
        if profiler is not None and index == prof_from:
            profiler.enable()
        started = time.perf_counter()
        report = await orchestrator.advance_phase(seeded.world, index, {}, drain_queue=True)
        wall = (time.perf_counter() - started) * 1000
        if profiler is not None and index == prof_to:
            profiler.disable()
        q1, s1 = meter.snapshot()
        beats.append(
            {
                "beat": index,
                "wall_ms": round(wall, 1),
                "sql": q1 - q0,
                "sql_ms": round((s1 - s0) * 1000, 1),
                "checkouts": meter.checkouts - c0,
                "scenes": len(report.scenes),
                "timings": report.timings_ms,
            }
        )
        if shapes_before is not None and args.sql_top:
            delta = {k: v - shapes_before.get(k, 0) for k, v in meter.by_shape.items()}
            top = sorted(((v, k) for k, v in delta.items() if v), reverse=True)[: args.sql_top]
            print(f"--- beat {index}: top statements ---")
            for v, k in top:
                print(f"{v:5d}  {k}")
        if index in checkpoints or index == args.beats:
            window = beats[-min(10, len(beats)) :]
            print(
                f"beat {index:>4}: wall p50 "
                f"{statistics.median(b['wall_ms'] for b in window):7.1f} ms"
                f"  sql {statistics.median(b['sql'] for b in window):6.0f} q"
                f"  sql {statistics.median(b['sql_ms'] for b in window):6.1f} ms"
                f"  scenes {statistics.median(b['scenes'] for b in window):3.0f}"
                f"  sessions {statistics.median(b['checkouts'] for b in window):4.0f}",
                flush=True,
            )
    stored = await checkpoint_storage(engine, seeded.world, args.beats)
    print(f"checkpoints: {stored}")
    await engine.dispose()

    out: dict[str, Any] = {
        "cast": args.cast,
        "places": args.places,
        "beats": beats,
        "calls": script.calls,
        "top_tables": sorted(meter.by_table.items(), key=lambda kv: -kv[1])[:25],
        "checkpoints": stored,
    }
    if profiler is not None:
        buf = io.StringIO()
        stats = pstats.Stats(profiler, stream=buf).sort_stats("cumulative")
        stats.print_stats(45)
        buf.write("\n--- by own time ---\n")
        stats.sort_stats("tottime").print_stats(35)
        out["profile"] = buf.getvalue()
        if args.prof_out:
            Path(args.prof_out).write_text(buf.getvalue(), encoding="utf-8")  # noqa: ASYNC240
            profiler.dump_stats(str(Path(args.prof_out).with_suffix(".prof")))
    return out


async def checkpoint_storage(engine: Any, world: UUID, latest: int) -> dict[str, Any]:
    """What the story's kept turns hold, and what a prune costs once they are pruned."""
    from sqlalchemy import text

    from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT count(*), coalesce(sum(pg_column_size(state)), 0),"
                    " coalesce(sum(octet_length(state::text)), 0),"
                    " pg_total_relation_size('story_checkpoint')"
                    " FROM story_checkpoint WHERE world_id = :w"
                ),
                {"w": world},
            )
        ).one()
    timings: list[float] = []
    for _ in range(20):
        async with create_unit_of_work(engine) as uow:
            started = time.perf_counter()
            await uow.checkpoints.prune(world, latest)
            timings.append((time.perf_counter() - started) * 1000)
            await uow.commit()
    return {
        "rows": int(row[0]),
        "stored_bytes": int(row[1]),
        "json_bytes": int(row[2]),
        "table_bytes": int(row[3]),
        "prune_noop_ms_p50": round(statistics.median(timings), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--cast", type=int, default=3)
    parser.add_argument("--places", type=int, default=6)
    parser.add_argument("--beats", type=int, default=30)
    parser.add_argument("--checkpoints", default="10,50,100,200,300")
    parser.add_argument("--profile", help="beat window to profile, e.g. 90:100")
    parser.add_argument("--prof-out")
    parser.add_argument("--dump", help="directory for the first prompts of each role")
    parser.add_argument("--json")
    parser.add_argument(
        "--cite", type=float, default=0.0, help="share of sources day-end summaries cite"
    )
    parser.add_argument(
        "--salient-cap", type=int, help="override OLDER_SALIENT_KEPT (old salient rows kept)"
    )
    parser.add_argument(
        "--bystanders",
        type=int,
        default=2,
        help="who else answers an attempt (the production default 2; -1 = everyone)",
    )
    parser.add_argument(
        "--sql-top", type=int, default=0, help="print top statements at checkpoints"
    )
    parser.add_argument("--no-reset", action="store_true", help="reuse the bench database")
    parser.add_argument(
        "--verify-reads", action="store_true", help="check shared reads against fresh ones"
    )
    parser.add_argument("--keep-turns", type=int, help="override KEEP_RECENT_TURNS (retention)")
    args = parser.parse_args()
    if args.keep_turns is not None:
        from worldsim.domain import branches

        branches.KEEP_RECENT_TURNS = args.keep_turns
    if args.salient_cap is not None:
        from worldsim.application.orchestration import stage1

        stage1.OLDER_SALIENT_KEPT = args.salient_cap
    if args.verify_reads:
        from worldsim.application.orchestration import phase_reads

        phase_reads.VERIFY = True
    os.environ["WORLDSIM_PROVIDER__ACTIVE_PROFILE"] = "fake"
    os.environ.setdefault("WORLDSIM_AUTOPLAY__ENABLED", "false")
    os.environ.pop("WORLDSIM_LOCAL_MODELS__URL", None)
    if args.no_reset:
        base = os.environ["WORLDSIM_DATABASE__URL"]
        os.environ["WORLDSIM_DATABASE__URL"] = re.sub(r"/[^/]+$", f"/{BENCH_DB}", base)
    else:
        fresh_database()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    result = asyncio.run(run(args))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1), encoding="utf-8")
    walls = [b["wall_ms"] for b in result["beats"]]
    print(f"calls: {result['calls']}")
    print(f"all beats: mean {statistics.mean(walls):.1f} ms, total {sum(walls) / 1000:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
