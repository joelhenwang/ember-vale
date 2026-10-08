"""Several API processes share one database connection budget (perf-reads-001)."""

from __future__ import annotations

from worldsim.interfaces.cli import pool_share


def test_one_process_keeps_the_configured_pool() -> None:
    assert pool_share(10, 20, 150, 1) == (10, 20)


def test_processes_never_exceed_the_budget_together() -> None:
    for workers in range(1, 33):
        pool, overflow = pool_share(10, 20, 150, workers)
        assert pool >= 1
        assert (pool + overflow) * workers <= max(150, 2 * workers)


def test_four_processes_fit_where_they_used_to_overrun() -> None:
    # 4 x (10 + 20) = 120 overran Postgres' default 100; the budget now caps it.
    assert pool_share(10, 20, 100, 4) == (10, 15)
