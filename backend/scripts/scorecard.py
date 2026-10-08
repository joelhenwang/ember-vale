"""Story scorecard: fixed scenarios on the live model, comparable metrics.

Each scenario seeds its own small world (people, places, items, starting
intentions) in a fresh scratch database, runs N beats through the same
path as manual Step and autoplay (``run_beat``), then scores the run from
the database: repairs per call, repeated questions, moves that land,
idle/talk-only streaks, the action mix, time and spend, plus one pass/fail
goal per scenario. Results go to ``docs/evidence/scorecard-NNN/`` (never
overwritten) so runs compare over time.

Live model calls cost money: the run needs ``--live`` and stops once the
estimated spend passes ``--max-usd``. Provider settings come from the
repo ``.env`` (only WORLDSIM_PROVIDER__* and the database URL are read).

Usage (from backend/):
    uv run python scripts/scorecard.py --live [--beats 8] [--max-usd 0.20]
        [--only strangers,lost_item] [--keep-db]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "evidence"


# --- environment -------------------------------------------------------------


def load_live_env() -> None:
    """Provider settings and the database URL from the repo .env, nothing else."""
    for raw in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip().replace("\r", "")
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key.startswith("WORLDSIM_PROVIDER__") or key == "WORLDSIM_DATABASE__URL":
            os.environ[key] = value.replace("@db:5432", "@localhost:5433")
    os.environ.setdefault("WORLDSIM_AUTOPLAY__ENABLED", "false")


def scratch_database() -> str:
    """Create and migrate a fresh database; point the process at it."""
    from alembic import command as alembic_command
    from alembic.config import Config
    from psycopg import connect, sql

    from worldsim.infrastructure.db.urls import to_sync_url

    base = os.environ["WORLDSIM_DATABASE__URL"]
    name = f"scorecard_{datetime.now(UTC):%Y%m%d_%H%M%S}"
    admin_url = re.sub(r"/[^/]+$", "/postgres", to_sync_url(base))
    with connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    os.environ["WORLDSIM_DATABASE__URL"] = re.sub(r"/[^/]+$", f"/{name}", base)
    config = Config()
    config.set_main_option("script_location", str(REPO / "backend" / "migrations"))
    alembic_command.upgrade(config, "head")
    return name


def drop_database(name: str) -> None:
    from psycopg import connect, sql

    from worldsim.infrastructure.db.urls import to_sync_url

    admin_url = re.sub(r"/[^/]+$", "/postgres", to_sync_url(os.environ["WORLDSIM_DATABASE__URL"]))
    with connect(admin_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )


# --- scenarios ---------------------------------------------------------------


@dataclass
class Person:
    key: str
    name: str
    place: str
    personality: str
    intention: str | None = None


@dataclass
class Thing:
    key: str
    name: str
    description: str
    place: str


@dataclass
class Scenario:
    key: str
    title: str
    people: list[Person]
    things: list[Thing] = field(default_factory=list)
    places: tuple[str, ...] = ("Hearth", "Market")
    #: Goal over the final state: (passed, explanation).
    goal: Callable[[dict[str, Any]], tuple[bool, str]] = lambda _s: (True, "")


WREN = "Quick, curious, warm. Wants: to learn what is going on in the vale."
ASH = "Patient, dry-witted, dependable. Market ward born and bred."


def _goal_strangers(s: dict[str, Any]) -> tuple[bool, str]:
    rate = s["repetition_rate"]
    return rate <= 0.2, f"repeated questions {rate:.0%} (pass ≤ 20%)"


def _goal_lost_item(s: dict[str, Any]) -> tuple[bool, str]:
    holder = s["items"].get("Lost purse", {}).get("holder")
    return holder is not None, f"purse held by {holder or 'nobody'}"


def _goal_stuck_task(s: dict[str, Any]) -> tuple[bool, str]:
    worked = s["interact_success"]
    return worked > 0, f"{worked} successful physical attempt(s)"


def _goal_meet_up(s: dict[str, Any]) -> tuple[bool, str]:
    places = s["final_places"]
    together = places.get("Wren") is not None and places.get("Wren") == places.get("Ash")
    return together, f"Wren at {places.get('Wren')}, Ash at {places.get('Ash')}"


def _goal_crowd(s: dict[str, Any]) -> tuple[bool, str]:
    rate = s["repetition_rate"]
    speakers = s["speakers"]
    return rate <= 0.2 and speakers >= 4, (
        f"{speakers} people spoke (pass ≥ 4); repeated questions {rate:.0%} (pass ≤ 20%)"
    )


def _goal_named_place(s: dict[str, Any]) -> tuple[bool, str]:
    mills = [name for name in s["all_places"] if "mill" in name.lower()]
    there = [who for who, place in s["final_places"].items() if place in mills]
    if not mills:
        return False, "no mill was added"
    return bool(there), f"added {mills[0]}; there at the end: {', '.join(there) or 'nobody'}"


SCENARIOS: list[Scenario] = [
    Scenario(
        key="strangers",
        title="Two strangers at the Hearth",
        people=[
            Person("wren", "Wren", "Hearth", WREN),
            Person("ash", "Ash", "Hearth", ASH),
        ],
        goal=_goal_strangers,
    ),
    Scenario(
        key="lost_item",
        title="A purse lies at the Market",
        people=[
            Person(
                "wren",
                "Wren",
                "Hearth",
                WREN + "\nWants: to see lost things back with their owners.",
            ),
            Person("ash", "Ash", "Market", ASH),
        ],
        things=[
            Thing(
                "purse",
                "Lost purse",
                "A small leather purse with a frayed cord and a shopping list inside.",
                "Market",
            )
        ],
        goal=_goal_lost_item,
    ),
    Scenario(
        key="stuck_task",
        title="A cart wheel stuck at the Market",
        people=[
            Person("wren", "Wren", "Market", WREN),
            Person("ash", "Ash", "Market", ASH),
            Person(
                "marg",
                "Old Marg",
                "Market",
                "A stallholder, gruff but fair. Wants: her cart wheel freed from the rut "
                "before the market opens.",
            ),
        ],
        goal=_goal_stuck_task,
    ),
    Scenario(
        key="meet_up",
        title="Two friends agree to meet at the Market",
        people=[
            Person("wren", "Wren", "Hearth", WREN, intention="meet Ash at the Market"),
            Person("ash", "Ash", "Market", ASH, intention="wait for Wren at the Market"),
        ],
        goal=_goal_meet_up,
    ),
    Scenario(
        key="crowd",
        title="Market morning: seven people at the stalls",
        people=[
            Person("wren", "Wren", "Market", WREN),
            Person("ash", "Ash", "Market", ASH),
            Person(
                "marg",
                "Old Marg",
                "Market",
                "A stallholder, gruff but fair. Wants: to sell her last baskets of apples.",
            ),
            Person(
                "tobin",
                "Tobin",
                "Market",
                "A young courier, breathless and gossipy. Wants: news worth carrying.",
            ),
            Person(
                "sela",
                "Sela",
                "Market",
                "A healer passing through, calm and watchful. Wants: someone who needs help.",
            ),
            Person(
                "brann",
                "Brann",
                "Market",
                "A burly carter, loud and generous. Wants: a hand loading his cart.",
            ),
            Person(
                "ivy",
                "Ivy",
                "Market",
                "A shy apprentice scribe. Wants: to work up the courage to ask about "
                "the vale's old tales.",
            ),
        ],
        goal=_goal_crowd,
    ),
    Scenario(
        key="named_place",
        title="Wren wants to visit the old mill, which is not on the map",
        people=[
            Person(
                "wren",
                "Wren",
                "Market",
                WREN + "\nWants: to visit her uncle, the miller, at the old mill.",
                intention="find the way to the old mill and see my uncle",
            ),
            Person("ash", "Ash", "Market", ASH),
        ],
        goal=_goal_named_place,
    ),
]


async def seed(scenario: Scenario) -> dict[str, UUID]:
    from worldsim.domain.characters import Character, CharacterCard
    from worldsim.domain.ids import (
        new_card_id,
        new_character_id,
        new_location_id,
        new_world_id,
    )
    from worldsim.domain.intentions import CharacterIntention
    from worldsim.domain.progress import ItemInstance
    from worldsim.domain.world import Location, Route, World
    from worldsim.infrastructure.db.engine import create_engine
    from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
    from worldsim.infrastructure.settings import Settings

    engine = create_engine(Settings())
    ids: dict[str, UUID] = {}
    try:
        async with create_unit_of_work(engine) as uow:
            world = new_world_id()
            ids["world"] = world
            await uow.worlds.add(World(id=world, name=scenario.title, seed_version="scorecard"))
            place_ids = {name: new_location_id() for name in scenario.places}
            for name, place in place_ids.items():
                routes = [
                    Route(
                        id=uuid4(), destination_location_id=other, duration_phases=1, stamina_cost=5
                    )
                    for other_name, other in place_ids.items()
                    if other_name != name
                ]
                await uow.locations.add(
                    Location(
                        id=place, world_id=world, name=name, region="Ember Vale", routes=routes
                    )
                )
                ids[f"place:{name}"] = place
            for person in scenario.people:
                cid = new_character_id()
                ids[person.key] = cid
                await uow.characters.add_identity(cid, world, person.name)
                await uow.characters.add_card(
                    CharacterCard(
                        id=new_card_id(),
                        character_id=cid,
                        name=person.name,
                        personality=person.personality,
                        version=1,
                    )
                )
                await uow.characters.add_state(
                    Character(
                        id=cid,
                        world_id=world,
                        name=person.name,
                        card_version=1,
                        location_id=place_ids[person.place],
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(cid, world, "character")
                if person.intention:
                    await uow.intentions.set(
                        CharacterIntention(
                            character_id=cid,
                            world_id=world,
                            text=person.intention,
                            set_phase_index=0,
                        )
                    )
            for thing in scenario.things:
                item = uuid4()
                ids[f"item:{thing.key}"] = item
                await uow.inventory.add_item(
                    ItemInstance(
                        id=item,
                        world_id=world,
                        item_key="found_object",
                        location_id=place_ids[thing.place],
                        name=thing.name,
                        description=thing.description,
                    )
                )
            await uow.versions.ensure(world, world, "world")
            await uow.commit()
    finally:
        await engine.dispose()
    return ids


# --- running -----------------------------------------------------------------


@dataclass
class Spend:
    limit_usd: float
    spent: float = 0.0

    def over(self) -> bool:
        return self.spent >= self.limit_usd


async def run_scenario(
    state: Any,
    scenario: Scenario,
    beats: int,
    spend: Spend,
    refresh_spend: Callable[[], Awaitable[None]],
    provider_dead: Callable[[UUID], Awaitable[bool]],
) -> dict[str, Any]:
    from worldsim.interfaces.http.beats import run_beat

    ids = await seed(scenario)
    world = ids["world"]
    times: list[float] = []
    error: str | None = None
    for index in range(1, beats + 1):
        if spend.over():
            error = f"stopped before beat {index}: spend cap reached"
            break
        started = time.monotonic()
        try:
            await run_beat(state, world, index, owner_prefix="scorecard")
        except Exception as exc:  # recorded, the other scenarios continue
            error = f"beat {index}: {type(exc).__name__}: {exc}"[:300]
            break
        times.append(time.monotonic() - started)
        await refresh_spend()  # across all scenarios: one shared cap
        if index == 1 and await provider_dead(world):
            error = "every model call in beat 1 failed (provider down or key out of credit)"
            break
    return {"ids": ids, "beat_seconds": times, "error": error}


# --- scoring -----------------------------------------------------------------


_WORD = re.compile(r"[a-z0-9']+")
#: Filler words that make different requests look alike.
_STOP = frozenset(
    "the and for you your with that this what are was have has its it's from about now "
    "let's lets ask asks asking tell more".split()
)
#: Calibrated on known runs: playtest-009's tale loop scores 43%, 010's "heave
#: on three" 24%, the progressing 011 and 005 runs 9% and 8%.
REPEAT_WINDOW = 3
REPEAT_OVERLAP = 0.6


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2 and w not in _STOP}


def repetition_rate(topics_by_author: dict[str, list[str]]) -> float:
    """Share of lines that mostly repeat one of the speaker's last few lines."""
    total = repeats = 0
    for topics in topics_by_author.values():
        seen: list[set[str]] = []
        for topic in topics:
            words = _tokens(topic)
            total += 1
            recent = seen[-REPEAT_WINDOW:]
            if any(
                words
                and prior
                and len(words & prior) / min(len(words), len(prior)) >= REPEAT_OVERLAP
                for prior in recent
            ):
                repeats += 1
            seen.append(words)
    return repeats / total if total else 0.0


def longest_streak(flags: list[bool]) -> int:
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def billed_usd(
    conn: Any, world: str, prompt_tokens: int, completion_tokens: int, prices: tuple[float, float]
) -> float:
    """The provider's bill for a world when recorded (model_cost), else list price."""
    row = conn.execute(
        "select count(*), coalesce(sum(prompt_cost_usd + completion_cost_usd), 0)"
        " from model_cost where world_id = %s",
        (world,),
    ).fetchone()
    if row and int(row[0]) > 0:
        return float(row[1])
    return prompt_tokens * prices[0] + completion_tokens * prices[1]


def score(
    conn: Any, scenario: Scenario, ids: dict[str, UUID], prices: tuple[float, float]
) -> dict[str, Any]:
    world = str(ids["world"])
    calls = conn.execute(
        "select role, status, prompt_tokens, completion_tokens, latency_ms,"
        " (request->>'prompt') like '%%previous output was rejected%%'"
        " from model_call where world_id = %s",
        (world,),
    ).fetchall()
    repairs = Counter(role for role, _s, _p, _c, _l, rejected in calls if rejected)
    prompt_tokens = sum(r[2] for r in calls)
    completion_tokens = sum(r[3] for r in calls)
    intents = conn.execute(
        "select pr.absolute_index, c.name, ci.family, ci.intent"
        " from character_intent ci join phase_run pr on pr.id = ci.phase_run_id"
        " join character c on c.id = ci.author_character_id"
        " where pr.world_id = %s order by pr.absolute_index, c.name",
        (world,),
    ).fetchall()
    mix = Counter(family for _i, _n, family, _x in intents)
    topics: dict[str, list[str]] = {}
    by_beat: dict[int, set[str]] = {}
    for index, name, family, body in intents:
        by_beat.setdefault(index, set()).add(family)
        if family == "communicate":
            action: dict[str, Any] = body.get("action") or {}
            topics.setdefault(name, []).append(str(action.get("topic") or ""))
    idle = {"wait", "rest", "observe"}
    beats_sorted = [by_beat[i] for i in sorted(by_beat)]
    idle_flags = [families <= idle for families in beats_sorted]
    talk_flags = [
        families <= idle | {"communicate"} and "communicate" in families
        for families in beats_sorted
    ]
    moves_tried = mix.get("move", 0)
    moves_done = conn.execute(
        "select count(*) from event_effect ee join world_event we on we.id = ee.event_id"
        " where we.world_id = %s and ee.effect_type = 'move_entity'",
        (world,),
    ).fetchone()[0]
    interact_success = conn.execute(
        "select count(*) from character_intent ci"
        " join scene s on s.phase_run_id = ci.phase_run_id"
        " join scene_participant sp on sp.scene_id = s.id"
        " and sp.character_id = ci.author_character_id"
        " join resolution r on r.scene_id = s.id"
        " where ci.world_id = %s and ci.family = 'interact'"
        " and r.outcome in ('success', 'partial')",
        (world,),
    ).fetchone()[0]
    hooks = conn.execute(
        "select title, requested_powers, status, ending from narrative_hook where world_id = %s",
        (world,),
    ).fetchall()
    all_places = [
        row[0] for row in conn.execute("select name from location where world_id = %s", (world,))
    ]
    final_places = dict(
        conn.execute(
            "select c.name, l.name from character_state cs"
            " join character c on c.id = cs.character_id"
            " join location l on l.id = cs.location_id where cs.world_id = %s",
            (world,),
        ).fetchall()
    )
    items = {
        name: {"holder": holder, "place": place}
        for name, holder, place in conn.execute(
            "select coalesce(i.name, i.item_key),"
            " (select name from character where id = i.owner_id),"
            " (select name from location where id = i.location_id)"
            " from item_instance i where i.world_id = %s",
            (world,),
        ).fetchall()
    }
    summaries = conn.execute(
        "select count(*), count(*) filter (where result->>'finish_reason' = 'length')"
        " from model_call where world_id = %s and role = 'daily_summary'",
        (world,),
    ).fetchone()
    stats: dict[str, Any] = {
        "calls": len(calls),
        "calls_by_role": dict(Counter(role for role, *_rest in calls)),
        "summaries": int(summaries[0]) if summaries else 0,
        "summaries_cut_off": int(summaries[1]) if summaries else 0,
        "speakers": sum(1 for said in topics.values() if said),
        "failed_calls": sum(1 for r in calls if r[1] != "succeeded"),
        "repairs": sum(repairs.values()),
        "repairs_by_role": dict(repairs),
        "repair_rate": sum(repairs.values()) / len(calls) if calls else 0.0,
        "est_usd": billed_usd(conn, world, prompt_tokens, completion_tokens, prices),
        "action_mix": dict(mix),
        "repetition_rate": repetition_rate(topics),
        "longest_idle_streak": longest_streak(idle_flags),
        "longest_talk_streak": longest_streak(talk_flags),
        "moves_tried": moves_tried,
        "moves_done": moves_done,
        "interact_success": interact_success,
        "hooks": [{"title": t, "powers": p, "status": st, "ending": e} for t, p, st, e in hooks],
        "settled": sum(1 for _t, _p, st, _e in hooks if st == "closed"),
        "final_places": final_places,
        "all_places": all_places,
        "items": items,
    }
    passed, why = scenario.goal(stats)
    stats["goal_passed"] = passed
    stats["goal_detail"] = why
    return stats


# --- reporting ---------------------------------------------------------------


def next_out_dir() -> Path:
    taken = [int(p.name.split("-")[1]) for p in EVIDENCE.glob("scorecard-[0-9][0-9][0-9]")]
    out = EVIDENCE / f"scorecard-{(max(taken) + 1 if taken else 1):03d}"
    out.mkdir(parents=True)
    return out


def report(out: Path, meta: dict[str, Any], results: dict[str, Any]) -> str:
    rows = [
        "| Scenario | Goal | Beats | s/beat | Repairs | Repeats | Moves done/tried "
        "| Talk streak | Idle streak | Settled | ~$ |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, r in results.items():
        s = r["score"]
        secs = r["beat_seconds"]
        rows.append(
            f"| {key} | {'PASS' if s['goal_passed'] else 'FAIL'}: {s['goal_detail']} "
            f"| {len(secs)} | {sum(secs) / len(secs) if secs else 0:.0f} "
            f"| {s['repairs']}/{s['calls']} | {s['repetition_rate']:.0%} "
            f"| {s['moves_done']}/{s['moves_tried']} | {s['longest_talk_streak']} "
            f"| {s['longest_idle_streak']} | {s.get('settled', 0)}/{len(s['hooks'])} "
            f"| {s['est_usd']:.3f} |"
        )
        if r.get("error"):
            rows.append(f"| {key} error | {r['error']} | | | | | | | | | |")
    table = "\n".join(rows)
    text = (
        f"# Story scorecard {out.name}\n\n"
        f"Commit `{meta['commit']}`, model `{meta['model']}`, {meta['beats']} beats per "
        f"scenario, run {meta['at']}. Estimated spend ${meta['est_usd_total']:.3f}.\n\n"
        f"{table}\n\nFull numbers (action mix, repairs by role, hooks, final places, "
        "items) in `results.json`.\n"
    )
    (out / "README.md").write_text(text, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps({"meta": meta, "results": results}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return table


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO
    ).stdout.strip()


def venice_prices(model: str, base_url: str, key: str) -> tuple[float, float]:
    """Per-token USD prices from Venice's model list (published per million)."""
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/models?type=text", headers={"Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))["data"]
    entry = next((m for m in data if m["id"] == model), None)
    if entry is None:
        raise SystemExit(f"no Venice pricing for {model}")
    pricing = entry["model_spec"]["pricing"]
    return float(pricing["input"]["usd"]) / 1e6, float(pricing["output"]["usd"]) / 1e6


def openrouter_prices(model: str) -> tuple[float, float]:
    with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))["data"]
    entry = next((m for m in data if m["id"] == model), None)
    if entry is None:
        raise SystemExit(f"no public pricing for {model}")
    return float(entry["pricing"]["prompt"]), float(entry["pricing"]["completion"])


# --- main ----------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> int:
    from psycopg import connect

    from worldsim.infrastructure.db.urls import to_sync_url
    from worldsim.infrastructure.settings import Settings
    from worldsim.interfaces.http.state import build_state

    settings = Settings()
    provider = settings.provider
    if provider.active_profile not in ("openrouter", "venice"):
        raise SystemExit("the scorecard measures the live model; .env selects no live provider")
    model = provider.default_model()
    if provider.active_profile == "venice":
        assert provider.venice_api_key is not None
        prices = venice_prices(
            model, provider.venice_base_url, provider.venice_api_key.get_secret_value()
        )
    else:
        prices = openrouter_prices(model)
    chosen = [s for s in SCENARIOS if not args.only or s.key in args.only.split(",")]
    state = build_state(settings, migrations_dir=REPO / "backend" / "migrations")
    dsn = to_sync_url(os.environ["WORLDSIM_DATABASE__URL"])
    spend = Spend(args.max_usd)

    def spent_so_far() -> float:
        """What the provider billed (model_cost), list price only where it did not say.

        List-price estimates ran ~3x under OpenRouter's bill with throughput
        routing (crowd runs 2026-10-08: est $0.40, billed $1.01), so the
        --max-usd guard must count the bill.
        """
        with connect(dsn) as conn:
            row = conn.execute(
                "select coalesce(sum(mc.prompt_cost_usd + mc.completion_cost_usd), 0),"
                " coalesce(sum(c.prompt_tokens) filter (where mc.call_id is null), 0),"
                " coalesce(sum(c.completion_tokens) filter (where mc.call_id is null), 0)"
                " from model_call c left join model_cost mc on mc.call_id = c.id"
            ).fetchone()
        billed, prompt, completion = (float(row[0]), int(row[1]), int(row[2])) if row else (0, 0, 0)
        return billed + prompt * prices[0] + completion * prices[1]

    async def refresh_spend() -> None:
        spend.spent = await asyncio.to_thread(spent_so_far)

    def _all_failed(world: UUID) -> bool:
        with connect(dsn) as conn:
            row = conn.execute(
                "select count(*), count(*) filter (where status <> 'succeeded')"
                " from model_call where world_id = %s",
                (str(world),),
            ).fetchone()
        return bool(row and row[0] > 0 and row[0] == row[1])

    async def provider_dead(world: UUID) -> bool:
        return await asyncio.to_thread(_all_failed, world)

    started = time.monotonic()
    runs = await asyncio.gather(
        *(run_scenario(state, s, args.beats, spend, refresh_spend, provider_dead) for s in chosen)
    )
    results: dict[str, Any] = {}
    with connect(dsn) as conn:
        for scenario, run in zip(chosen, runs, strict=True):
            results[scenario.key] = {
                **run,
                "ids": {k: str(v) for k, v in run["ids"].items()},
                "score": score(conn, scenario, run["ids"], prices),
            }
    await state.engine.dispose()
    commit = args.code_label or await asyncio.to_thread(_commit)
    meta = {
        "commit": commit,
        "provider": provider.active_profile,
        "model": model,
        "beats": args.beats,
        #: WORLDSIM_APP__REACTING_BYSTANDERS (None: everyone present reacts).
        "reacting_bystanders": settings.app.reacting_bystanders,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "wall_seconds": round(time.monotonic() - started),
        "est_usd_total": spent_so_far(),
        "scenarios": [s.key for s in chosen],
    }
    out = next_out_dir()
    print(report(out, meta, results))
    print(f"\nwrote {out.relative_to(REPO)}; estimated spend ${meta['est_usd_total']:.3f}")
    return 0 if all(r["score"]["goal_passed"] for r in results.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Story scorecard on the live model.")
    parser.add_argument("--live", action="store_true", help="required: spends real credit")
    parser.add_argument("--beats", type=int, default=8)
    parser.add_argument("--max-usd", type=float, default=0.20)
    parser.add_argument("--only", default="", help="comma-separated scenario keys")
    parser.add_argument(
        "--provider",
        choices=("openrouter", "venice"),
        help="override WORLDSIM_PROVIDER__ACTIVE_PROFILE from .env for this run",
    )
    parser.add_argument("--keep-db", action="store_true", help="keep the scratch database")
    parser.add_argument(
        "--code-label",
        default="",
        help="record this instead of git HEAD (e.g. a baseline run via PYTHONPATH)",
    )
    args = parser.parse_args()
    if not args.live:
        print("refusing to run without --live (this spends real model credit)", file=sys.stderr)
        return 2
    # Results carry characters like "≤"; the Windows console default is cp1252.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    load_live_env()
    if args.provider:
        os.environ["WORLDSIM_PROVIDER__ACTIVE_PROFILE"] = args.provider
    name = scratch_database()
    print(f"scratch database {name}")
    scored = False
    try:
        code = asyncio.run(main_async(args))
        scored = True
        return code
    finally:
        if scored and not args.keep_db:
            drop_database(name)
        else:
            print(f"kept scratch database {name} for inspection or re-scoring", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
