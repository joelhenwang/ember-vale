"""Where a scene happened: where everyone ends up, when that is one place."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from worldsim.application.orchestration.stage1 import scene_location
from worldsim.domain.effects import MoveEntityEffect

ASH, WREN = uuid4(), uuid4()
MARKET, HEARTH, WELL = uuid4(), uuid4(), uuid4()


def _scene(*people: Any) -> Any:
    return SimpleNamespace(participants=[SimpleNamespace(character_id=p) for p in people])


def _walk(who: Any, start: Any, end: Any) -> MoveEntityEffect:
    return MoveEntityEffect(
        affected_ids=[who],
        expected_versions={str(who): 1},
        from_location_id=start,
        to_location_id=end,
    )


def test_a_traveller_meeting_a_friend_happens_where_they_meet() -> None:
    starts = {ASH: MARKET, WREN: HEARTH}
    # Ash is listed first and walked from the Market to Wren at the Hearth.
    assert scene_location(_scene(ASH, WREN), starts, [_walk(ASH, MARKET, HEARTH)]) == HEARTH


def test_people_who_end_apart_keep_the_first_ones_starting_place() -> None:
    starts = {ASH: MARKET, WREN: MARKET}
    assert scene_location(_scene(ASH, WREN), starts, [_walk(WREN, MARKET, WELL)]) == MARKET


def test_a_scene_without_moves_stays_put() -> None:
    assert scene_location(_scene(ASH), {ASH: WELL}, []) == WELL
