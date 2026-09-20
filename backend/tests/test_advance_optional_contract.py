"""Optional-but-not-nullable request fields (third-push review R1).

`player_intents` is declared `dict[...] = Field(default_factory=dict)`:
omission and `{}` are accepted, explicit null is rejected. The frontend
omits the field when there are no intents; this pins the server side of
that contract.
"""

import uuid

import pytest
from pydantic import ValidationError

from worldsim.interfaces.http import schemas as api


def _base(**overrides):
    body = {"world_id": str(uuid.uuid4()), "absolute_index": 1}
    body.update(overrides)
    return body


def test_player_intents_omitted_ok():
    assert api.Stage1AdvanceRequest(**_base()).player_intents == {}


def test_player_intents_empty_ok():
    assert api.Stage1AdvanceRequest(**_base(player_intents={})).player_intents == {}


def test_player_intents_null_rejected():
    with pytest.raises(ValidationError):
        api.Stage1AdvanceRequest(**_base(player_intents=None))


def test_draft_payload_null_rejected():
    with pytest.raises(ValidationError):
        api.StoryDraftCreateRequest(payload=None, current_step="world")
