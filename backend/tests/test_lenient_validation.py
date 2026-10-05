"""Model JSON clean-up that saves a repair round trip."""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import TypeAdapter, ValidationError

from worldsim.application.graphs.lenient import (
    fill_expected_versions,
    repair_detail,
    validate_lenient,
)
from worldsim.domain.commands import ActionIntent
from worldsim.domain.director import DirectorProposal
from worldsim.domain.resolution import ResolverProposal

ACTIONS: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)
DIRECTOR: TypeAdapter[DirectorProposal] = TypeAdapter(DirectorProposal)
RESOLVER: TypeAdapter[ResolverProposal] = TypeAdapter(ResolverProposal)


def test_wait_with_every_other_field_null_is_accepted() -> None:
    # Live DeepSeek output that cost a repair call (beat-latency-001).
    raw = json.dumps(
        {
            "character_id": str(uuid.uuid4()),
            "snapshot_id": str(uuid.uuid4()),
            "family": "wait",
            "focus": None,
            "destination_location_id": None,
            "route_id": None,
            "target_character_id": None,
            "topic": None,
        }
    )
    assert validate_lenient(ACTIONS, raw).family == "wait"


def test_director_stray_type_key_is_dropped() -> None:
    raw = '{"type": "json_object", "action": "noop", "reason": "nothing pressing"}'
    assert validate_lenient(DIRECTOR, raw).action == "noop"


def test_real_errors_still_go_to_repair() -> None:
    missing = json.dumps({"family": "communicate", "character_id": str(uuid.uuid4())})
    with pytest.raises(ValidationError):
        validate_lenient(ACTIONS, missing)
    mixed = json.dumps({"family": "wait", "character_id": "nope", "extra": 1})
    with pytest.raises(ValidationError):
        validate_lenient(ACTIONS, mixed)
    with pytest.raises(ValidationError):
        validate_lenient(ACTIONS, "{not json")


def test_resolver_versions_come_from_the_server() -> None:
    wren = str(uuid.uuid4())
    raw = json.dumps(
        {
            "outcome": "success",
            "rationale": "They talk.",
            "effects": [
                {
                    "effect_type": "record_observation",
                    "affected_ids": [wren],
                    "observer_character_id": wren,
                    "facts": [{"key": "greeting", "value": "heard"}],
                    "expected_versions": {},
                }
            ],
        }
    )
    with pytest.raises(ValidationError):
        RESOLVER.validate_json(raw)  # what used to trigger a repair
    proposal = validate_lenient(RESOLVER, fill_expected_versions(raw, {wren: 7}))
    assert proposal.effects[0].expected_versions == {wren: 7}


def test_fill_versions_overrides_model_guesses_and_ignores_garbage() -> None:
    wren = str(uuid.uuid4())
    raw = json.dumps({"effects": [{"affected_ids": [wren], "expected_versions": {wren: 99}}]})
    assert json.loads(fill_expected_versions(raw, {wren: 3}))["effects"][0][
        "expected_versions"
    ] == {wren: 3}
    assert fill_expected_versions("[1]", {wren: 3}) == "[1]"
    assert fill_expected_versions("{oops", {wren: 3}) == "{oops"


def test_repair_detail_names_fields() -> None:
    with pytest.raises(ValidationError) as caught:
        ACTIONS.validate_json(json.dumps({"family": "communicate"}))
    detail = repair_detail(caught.value)
    assert "communicate." in detail and "Field required" in detail
