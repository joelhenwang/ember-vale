"""Who answers an attempt in a crowd (WORLDSIM_APP__REACTING_BYSTANDERS)."""

from __future__ import annotations

from uuid import UUID, uuid4

from worldsim.application.orchestration.stage1 import choose_reactors

CROWD = [UUID(int=n) for n in range(1, 9)]


def test_without_a_cap_everyone_present_answers() -> None:
    assert choose_reactors(uuid4(), CROWD, CROWD[3], None) == CROWD


def test_with_a_cap_the_person_addressed_plus_a_few_answer() -> None:
    attempt = uuid4()
    chosen = choose_reactors(attempt, CROWD, CROWD[5], 2)
    assert CROWD[5] in chosen and len(chosen) == 3
    assert chosen == [c for c in CROWD if c in chosen]  # scene order kept
    assert choose_reactors(attempt, CROWD, CROWD[5], 2) == chosen  # replay-stable


def test_an_unaimed_attempt_gets_only_bystanders_and_they_vary() -> None:
    picks = {tuple(choose_reactors(uuid4(), CROWD, None, 2)) for _ in range(40)}
    assert all(len(p) == 2 for p in picks)
    assert len({c for p in picks for c in p}) == len(CROWD)  # spread over the crowd


def test_a_small_scene_is_untouched_by_the_cap() -> None:
    small = CROWD[:3]
    assert choose_reactors(uuid4(), small, small[0], 2) == small
