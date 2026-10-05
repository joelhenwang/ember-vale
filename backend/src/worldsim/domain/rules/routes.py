"""Route inference for moves: the model names where, the server knows how.

Character decisions name a destination from the listed routes but cannot
know route ids, and a move without a route is ruled impossible. Before
resolution the route is filled from the character's current place: the
shortest route to that destination, ties broken by id. Moves that
already name a route, or have no route to their destination, pass
through unchanged (the latter still resolve as impossible).
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from worldsim.domain.commands import ActionIntent, MoveAction
from worldsim.domain.world import Location


def with_route(
    action: ActionIntent, origin_id: UUID | None, places: Mapping[UUID, Location]
) -> ActionIntent:
    """The action with a route filled in when it is a routeless move."""
    if not isinstance(action, MoveAction) or action.route_id is not None or origin_id is None:
        return action
    origin = places.get(origin_id)
    if origin is None:
        return action
    routes = [
        r for r in origin.routes if r.destination_location_id == action.destination_location_id
    ]
    if not routes:
        return action
    best = min(routes, key=lambda r: (r.duration_phases, r.stamina_cost, r.id.hex))
    return action.model_copy(update={"route_id": best.id})
