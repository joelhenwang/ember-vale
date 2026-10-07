"""S0-API-001: CLI mirrors the boundary (owned by S0-API-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from worldsim.interfaces.cli import main

SEED_DIR = str(Path(__file__).parent.parent.parent / "content" / "seeds" / "stage0")


def test_cli_seed_inspect_reconcile(migrated_db: None, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["seed", "--seed-dir", SEED_DIR]) == 0
    seeded = json.loads(str(capsys.readouterr().out))
    assert seeded["seed_version"] == "stage0-v1"
    assert seeded["duplicate"] is False
    world_id = seeded["world_id"]

    assert main(["inspect", "world", "--world", world_id]) == 0
    inspected = json.loads(str(capsys.readouterr().out))
    assert len(inspected["characters"]) == 2
    assert len(inspected["locations"]) == 2
    assert inspected["open_run"] is None

    assert main(["inspect", "events", "--world", world_id, "--after", "0"]) == 0
    timeline = json.loads(str(capsys.readouterr().out))
    assert [entry["sequence"] for entry in timeline["entries"]] == [1]

    assert main(["reconcile", "--world", world_id]) == 0
    reconciled = json.loads(str(capsys.readouterr().out))
    assert reconciled["open_run_id"] is None


def test_cli_unknown_world_fails_cleanly(
    migrated_db: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["inspect", "world", "--world", "10000000-0000-4000-8000-000000009999"])
    assert code == 1
    err = str(capsys.readouterr().err)
    assert "NOT_FOUND" in err
