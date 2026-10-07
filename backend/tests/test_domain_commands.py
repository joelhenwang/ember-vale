import pytest
from pydantic import TypeAdapter, ValidationError

from worldsim.domain.commands import (
    ActionIntent,
    AuditMeta,
    MoveAction,
    RestAction,
    SeedWorldCommand,
    WaitAction,
)
from worldsim.domain.enums import ActionFamily, CommandType, UserRole
from worldsim.domain.ids import new_command_id, new_snapshot_id, new_world_id


def _audit() -> AuditMeta:
    return AuditMeta(requested_by="stage-scenario")


def _seed(**overrides: object) -> SeedWorldCommand:
    fields: dict[str, object] = {
        "command_id": new_command_id(),
        "idempotency_key": "seed-0001",
        "actor_role": UserRole.SYSTEM,
        "world_id": new_world_id(),
        "expected_versions": {},
        "audit": _audit(),
        "seed_version": "stage0-v1",
        "content_hash": "0" * 64,
    }
    return SeedWorldCommand.model_validate(fields | overrides)


def test_command_round_trip() -> None:
    command = _seed()
    assert command.command_type is CommandType.SEED_WORLD
    assert SeedWorldCommand.model_validate_json(command.model_dump_json()) == command


def test_command_rejects_extra_fields_and_empty_key() -> None:
    with pytest.raises(ValidationError):
        _seed(unknown_field="nope")
    with pytest.raises(ValidationError):
        _seed(idempotency_key="")


def test_action_intents_dispatch_on_family() -> None:
    adapter: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)
    character_id = new_command_id()
    snapshot_id = new_snapshot_id()
    wait = adapter.validate_python(
        {"family": "wait", "character_id": str(character_id), "snapshot_id": str(snapshot_id)}
    )
    assert isinstance(wait, WaitAction)
    assert wait.family is ActionFamily.WAIT
    move = adapter.validate_python(
        {
            "family": "move",
            "character_id": str(character_id),
            "snapshot_id": str(snapshot_id),
            "destination_location_id": str(new_world_id()),
        }
    )
    assert isinstance(move, MoveAction)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "family": "rest",
                "character_id": str(character_id),
                "snapshot_id": str(snapshot_id),
                "duration_phases": 0,
            }
        )
    rest = RestAction(character_id=character_id, snapshot_id=snapshot_id)
    assert rest.duration_phases == 1
    assert rest.model_validate_json(rest.model_dump_json()) == rest
