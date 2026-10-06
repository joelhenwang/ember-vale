"""An opening about a place that is not on the map gets one repair to add it.

Scorecard-005: the director answered the mill the characters kept naming
with a mill hook and no new_location, so nobody could reach the mill.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from worldsim.application.graphs.director import (
    DirectorGraphDeps,
    build_director_graph,
    load_director_prompt,
    overlooks_place,
)
from worldsim.application.graphs.runtime import invoke
from worldsim.application.graphs.state import GraphInvocation
from worldsim.domain.director import DirectorProposal
from worldsim.domain.ids import (
    new_arc_id,
    new_hook_id,
    new_location_id,
    new_phase_run_id,
    new_task_id,
    new_world_id,
)
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import DIRECTOR_FAKE_PROFILE

HEARTH = new_location_id()

MILL_HOOK: dict[str, Any] = {
    "action": "propose_hook",
    "title": "The miller's son needs a message carried",
    "purpose": "Someone must carry word to the old mill before dusk.",
    "requested_powers": [],
    "participant_ids": [],
    "reason": "",
}
MILL_HOOK_WITH_PLACE: dict[str, Any] = {
    **MILL_HOOK,
    "requested_powers": ["new_location"],
    "place": {"name": "Old Mill", "connect_to": str(HEARTH)},
}


def _proposal(**fields: Any) -> DirectorProposal:
    return DirectorProposal.model_validate({**MILL_HOOK, **fields})


def test_overlooks_place_matches_the_place_noun() -> None:
    assert overlooks_place(_proposal(), "Old Mill") is True
    assert overlooks_place(_proposal(title="Mills", purpose=""), "Old Mill") is True
    # "miller" alone is a person, not the place.
    assert overlooks_place(_proposal(purpose="Ask the miller."), "Old Mill") is False
    assert overlooks_place(_proposal(requested_powers=["new_location"]), "Old Mill") is False
    assert overlooks_place(_proposal(action="noop"), "Old Mill") is False
    assert overlooks_place(_proposal(), "Old Forge") is False


def _invocation(**extra: Any) -> GraphInvocation:
    world_id = new_world_id()
    return GraphInvocation(
        graph_name="director-proposal",
        graph_version="v1",
        task_run_id=new_task_id(),
        world_id=world_id,
        phase_run_id=new_phase_run_id(),
        snapshot_id=new_task_id(),
        role="director",
        profile_version=DIRECTOR_FAKE_PROFILE.version,
        prompt_version="director.v1",
        input={
            "world_summary": "Phase 4. Characters: Wren, Ash. Places: Hearth.",
            "trigger_ok": True,
            "known_character_ids": [],
            "active_hooks": 0,
            "active_arcs": 0,
            "hook_id": str(new_hook_id()),
            "arc_id": str(new_arc_id()),
            "world_id": str(world_id),
            "location_ids": [str(HEARTH)],
            "place_id": str(new_location_id()),
            "places_left": 3,
            "place_names": ["Hearth"],
            **extra,
        },
    )


def _run(replies: list[dict[str, Any]], **extra: Any) -> tuple[dict[str, Any], list[str]]:
    prompts: list[str] = []

    def _route(request: Any) -> str | None:
        if "You direct" not in (request.system or ""):
            return None
        prompts.append(request.prompt)
        return json.dumps(replies[min(len(prompts), len(replies)) - 1])

    gateway = FakeGateway(profile=DIRECTOR_FAKE_PROFILE)
    gateway.route = _route
    graph = build_director_graph(
        DirectorGraphDeps(
            gateway=gateway,
            profile=DIRECTOR_FAKE_PROFILE,
            system_template=load_director_prompt(),
        )
    )
    return asyncio.run(invoke(graph, _invocation(**extra))), prompts


MILL = {
    "unmapped_place": "Old Mill",
    "unmapped_from": str(HEARTH),
    "unmapped_from_name": "Hearth",
}


def test_mill_hook_without_the_mill_is_repaired_into_adding_it() -> None:
    result, prompts = _run([MILL_HOOK, MILL_HOOK_WITH_PLACE], **MILL)
    assert len(prompts) == 2
    assert '"name": "Old Mill"' in prompts[1] and str(HEARTH) in prompts[1]
    assert result["status"] == "proposed"
    assert result["decision"]["place"]["name"] == "Old Mill"
    assert result["repair_count"] == 1


def test_failed_place_repair_keeps_the_first_proposal() -> None:
    result, prompts = _run([MILL_HOOK, {"action": "nonsense"}], **MILL)
    assert len(prompts) == 2
    assert result["status"] == "proposed"
    assert result["decision"]["hook"]["title"] == MILL_HOOK["title"]
    assert result["decision"]["place"] is None


def test_no_unmapped_place_means_no_extra_call() -> None:
    result, prompts = _run([MILL_HOOK])
    assert len(prompts) == 1
    assert result["status"] == "proposed" and result["repair_count"] == 0
