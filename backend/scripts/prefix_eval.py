"""How much of each prompt repeats the same actor's previous prompt, by section order.

A provider's prompt cache can only reuse an unchanged prefix. For each
actor's consecutive decision/reaction prompts this measures the shared
prefix of the user prompt (the system prompt is identical for a role and
is cached either way) under the stored order and under another order,
by re-arranging the stored ``## section`` blocks. No model calls.

Result on the dev stories (2026-10-06): moving the steady sections first
(identity, goals, relationships, lore, memories, observations) raised the
shared prefix only from 44% to 46% for decisions and 45% to 49% for
reactions: the user prompt is short next to the system prompt, which
leads every call and is what the provider caches. The order was kept.

    uv run python scripts/prefix_eval.py --order "$ORDER"

where ORDER lists every section, comma-separated, e.g. identity,goals,
relationships,lore,memories,observations,surroundings,own_state,scene_attempts
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import statistics

from sqlalchemy import text

from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.settings import Settings

OLD = (
    "identity,surroundings,own_state,goals,relationships,observations,memories,lore,scene_attempts"
)


def sections(prompt: str) -> tuple[dict[str, str], str]:
    """Section blocks by name, plus whatever follows the last section."""
    parts = re.split(r"(?m)^## ", prompt)
    found: dict[str, str] = {}
    tail = ""
    for part in parts[1:]:
        name, _, body = part.partition("\n")
        found[name.strip()] = body
    if parts[1:]:
        last = parts[-1]
        # The closing instruction follows the last section after a blank line.
        body, sep, rest = last.partition("\n\nOutput ")
        if sep:
            found[last.partition("\n")[0].strip()] = body.partition("\n")[2]
            tail = "Output " + rest
    return found, tail


def arrange(prompt: str, order: list[str]) -> str:
    found, tail = sections(prompt)
    blocks = [f"## {name}\n{found[name]}" for name in order if name in found]
    return "\n\n".join(blocks) + ("\n\n" + tail if tail else "")


def shared(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


async def main(order: list[str], role: str, limit: int) -> None:
    engine = create_engine(Settings())
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT actor_id, request->>'prompt' AS prompt FROM model_call "
                    "WHERE role = :role AND status = 'succeeded' AND actor_id IS NOT NULL "
                    "AND request->>'prompt' LIKE '## identity%' "
                    "ORDER BY created_at DESC LIMIT :limit"
                ),
                {"role": role, "limit": limit},
            )
        ).all()
    await engine.dispose()
    by_actor: dict[str, list[str]] = {}
    for row in reversed(rows):
        by_actor.setdefault(str(row.actor_id), []).append(row.prompt)
    old_order = OLD.split(",")
    old_share: list[float] = []
    new_share: list[float] = []
    for prompts in by_actor.values():
        for before, after in zip(prompts, prompts[1:], strict=False):
            a, b = arrange(before, old_order), arrange(after, old_order)
            old_share.append(shared(a, b) / len(b))
            a, b = arrange(before, order), arrange(after, order)
            new_share.append(shared(a, b) / len(b))
    if not old_share:
        print("no consecutive prompts found")
        return
    print(f"{role}: {len(old_share)} consecutive pairs from {len(by_actor)} actors")
    print(f"  shared prefix, old order: mean {statistics.mean(old_share):.0%}")
    print(f"  shared prefix, new order: mean {statistics.mean(new_share):.0%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--order", required=True)
    parser.add_argument("--role", default="character_decision")
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    asyncio.run(main(args.order.split(","), args.role, args.limit))
