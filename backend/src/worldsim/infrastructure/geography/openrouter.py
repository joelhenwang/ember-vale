"""Read a world map with vision models on OpenRouter.

Two questions, two models: one finds the places, another traces the
roads between the places the player kept. The prompts are the ones
measured in docs/evidence/map-detect-001 and map-routes-001; the spots
inside one place (its own map) in docs/evidence/place-spots-001.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any, cast

import httpx
from PIL import Image

from worldsim.application.ports.map_reader import (
    MapReadingError,
    Reading,
    ReadPlace,
    ReadRoad,
)
from worldsim.domain.geography import MAP_SPAN, ROAD_KINDS

PLACES_PROMPT = """This is a fantasy world map. List every place a traveller could go to or through:
- settlements: city, town, village, port, camp, tribe
- sites: castle, fort, checkpoint, gate, tower, lighthouse, temple, monastery, chapel, inn,
  market, smithy, mill, farm, ruin, dungeon, cave, mine, bridge, landmark
- areas: forest, mountains, hills, swamp, lake, river, road, path, sea, island

For each place give:
- "name": the label written on the map for it, if there is one; otherwise a short description
- "kind": one word from the lists above
- "point": [x, y], the centre of the place's drawing (not of its label), as integers from 0 to
  1000 across the image's width (x) and height (y); [0, 0] is the top-left corner

Answer with JSON only: {"places": [{"name": "...", "kind": "...", "point": [x, y]}]}"""

ROADS_PROMPT = """These are the places on this fantasy map, with where each is drawn
([x, y] from 0 to 1000 across the image's width and height; [0, 0] is the top-left corner):
{places}

List every direct connection a traveller could use between two of these places, as drawn on
the map: roads, paths and tracks, bridges, sea or river routes drawn as lines, mountain passes.
"Direct" means the route goes from one place to the other without passing through a third
listed place; if it does, list the two shorter legs instead. Only include connections you can
see drawn; leave a place unconnected if no drawn route reaches it.

For each connection give:
- "from" and "to": the place numbers
- "by": one of road, path, sea, river, bridge, pass
- "points": 3 to 8 [x, y] points along the drawn route, from the first place to the second

Answer with JSON only:
{{"connections": [{{"from": 1, "to": 2, "by": "road", "points": [[x, y], [x, y], [x, y]]}}]}}"""

SPOTS_PROMPT = """This is a picture of one place in a fantasy world: a town, village, castle,
port or similar, seen from above or at an angle. List the spots inside it where a person
could be found:
- buildings: inn, tavern, house, hall, manor, keep, chapel, temple, shrine, smithy, mill,
  shop, workshop, stable, barn, warehouse, barracks, tower, gate
- open places: square, market, yard, garden, field, farm, graveyard, dock, pier, well,
  bridge, landmark, camp
- edges: forest, river, lake, road, path

List each distinct spot once. Ordinary houses only when one stands out, at most three.

For each spot give:
- "name": the label written on the picture for it, if there is one; otherwise a short name a
  local would call it by, from what it is and how it looks ("the Red Tower", "Fishmarket
  Steps", "the Old Gatehouse"); never words about the picture itself (left, right, upper,
  lower, foreground, background, centre, corner, near)
- "kind": one word from the lists above
- "point": [x, y], the centre of the spot's drawing (not of its label), as integers from 0 to
  1000 across the image's width (x) and height (y); [0, 0] is the top-left corner

Answer with JSON only: {"places": [{"name": "...", "kind": "...", "point": [x, y]}]}"""

FACE_PROMPT = """This picture shows a character. Give the box around the main character's face,
forehead to chin and ear to ear, as integers from 0 to 1000 across the image's width (x) and
height (y); [0, 0] is the top-left corner.

Answer with JSON only: {"face": [left, top, right, bottom]}, or {"face": null} when no face
is visible."""

KNOWN_PART = """

This world already has these places: {names}.
The map may show them without labels. When a drawn place fits one of them (its kind and
what the name suggests), use that exact name for it, each name at most once; give any other
place its own label or a short description as above."""


def places_prompt(known: tuple[str, ...] = ()) -> str:
    """The places question, told the world's own place names when there are any."""
    names = [n.strip() for n in known if n.strip()][:40]
    if not names:
        return PLACES_PROMPT
    head, _, answer = PLACES_PROMPT.rpartition("\n\nAnswer with JSON only")
    return head + KNOWN_PART.format(names=", ".join(names)) + "\n\nAnswer with JSON only" + answer


#: Larger pictures cost more and read no better.
MAX_SIDE = 2048


def _clamp(value: object) -> int:
    if not isinstance(value, int | float):
        raise TypeError("not a number")
    return max(0, min(MAP_SPAN, round(float(value))))


def _point(raw: object) -> tuple[int, int] | None:
    if isinstance(raw, list | tuple):
        pair = list(cast("list[object] | tuple[object, ...]", raw))
        if len(pair) == 2:
            try:
                return _clamp(pair[0]), _clamp(pair[1])
            except (TypeError, ValueError, OverflowError):
                return None
    return None


def _json(text: str) -> dict[str, object]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise MapReadingError("the map reader answered without JSON")
    try:
        data: object = json.loads(text[start : end + 1])
    except ValueError as exc:
        raise MapReadingError(f"the map reader's JSON is broken: {exc}") from exc
    if not isinstance(data, dict):
        raise MapReadingError("the map reader's JSON is not an object")
    return cast("dict[str, object]", data)


def _items(data: dict[str, object], key: str) -> list[dict[str, object]]:
    """The objects listed under one key; anything else is skipped."""
    raw = data.get(key)
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _text(raw: dict[str, object], key: str, default: str = "") -> str:
    value = raw.get(key)
    return str(value) if value is not None and value != "" else default


def parse_places(text: str) -> list[ReadPlace]:
    places: list[ReadPlace] = []
    for raw in _items(_json(text), "places"):
        point = _point(raw.get("point"))
        name = _text(raw, "name").strip()[:128]
        if point is None or not name:
            continue
        places.append(ReadPlace(name=name, kind=_text(raw, "kind").lower()[:32], point=point))
    return places


def parse_face(text: str) -> tuple[int, int, int, int] | None:
    raw = _json(text).get("face")
    if not isinstance(raw, list):
        return None
    values = cast("list[object]", raw)
    if len(values) != 4:
        return None
    try:
        left, top, right, bottom = (_clamp(v) for v in values)
    except (TypeError, ValueError, OverflowError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def parse_roads(text: str, count: int) -> list[ReadRoad]:
    roads: list[ReadRoad] = []
    seen: set[frozenset[int]] = set()
    for raw in _items(_json(text), "connections"):
        try:
            a, b = int(_text(raw, "from")) - 1, int(_text(raw, "to")) - 1
        except ValueError:
            continue
        pair = frozenset((a, b))
        if a == b or not (0 <= a < count and 0 <= b < count) or pair in seen:
            continue
        seen.add(pair)
        by = _text(raw, "by", "road").lower()
        bends = raw.get("points")
        listed = cast("list[object]", bends) if isinstance(bends, list) else []
        points = [p for p in (_point(q) for q in listed) if p is not None]
        roads.append(
            ReadRoad(a=a, b=b, by=by if by in ROAD_KINDS else "road", points=tuple(points[:16]))
        )
    return roads


def _data_url(image: bytes) -> str:
    """The map as a JPEG no larger than MAX_SIDE."""
    try:
        with Image.open(io.BytesIO(image)) as source:
            picture = source.convert("RGB")
    except (OSError, ValueError) as exc:
        raise MapReadingError(f"the map picture cannot be read: {exc}") from exc
    picture.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    picture.save(out, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


class OpenRouterMapReader:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        places_model: str,
        roads_model: str,
        reasoning: str | None = "low",
        max_tokens: int = 40000,
        timeout_s: float = 400.0,
    ) -> None:
        self._key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._places_model = places_model
        self._roads_model = roads_model
        self._reasoning = reasoning
        self._max_tokens = max_tokens
        self._timeout = timeout_s

    async def _ask(self, model: str, image: bytes, prompt: str) -> tuple[str, float, float]:
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "usage": {"include": True},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": _data_url(image)}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        if self._reasoning:
            body["reasoning"] = {"effort": self._reasoning}
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                reply = await client.post(
                    self._url, json=body, headers={"Authorization": f"Bearer {self._key}"}
                )
        except httpx.HTTPError as exc:
            raise MapReadingError(f"map reader unreachable: {type(exc).__name__}") from exc
        seconds = round(time.monotonic() - started, 1)
        if reply.status_code != 200:
            raise MapReadingError(f"map reader answered {reply.status_code}: {reply.text[:200]}")
        payload: dict[str, Any] = reply.json()
        usage: dict[str, Any] = payload.get("usage") or {}
        cost = float(usage.get("cost") or 0)
        try:
            choice: dict[str, Any] = payload["choices"][0]
            text = str(choice["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise MapReadingError("the map reader sent no answer") from exc
        if not text.strip():
            reason = choice.get("finish_reason")
            raise MapReadingError(f"the map reader gave up without answering ({reason})")
        return text, seconds, cost

    async def places(
        self, image: bytes, mime: str, known: tuple[str, ...] = ()
    ) -> Reading[ReadPlace]:
        del mime
        text, seconds, cost = await self._ask(self._places_model, image, places_prompt(known))
        return Reading(tuple(parse_places(text)), self._places_model, seconds, cost)

    async def face(self, image: bytes, mime: str) -> Reading[tuple[int, int, int, int]]:
        del mime
        text, seconds, cost = await self._ask(self._places_model, image, FACE_PROMPT)
        box = parse_face(text)
        return Reading((box,) if box else (), self._places_model, seconds, cost)

    async def spots(self, image: bytes, mime: str) -> Reading[ReadPlace]:
        del mime
        text, seconds, cost = await self._ask(self._places_model, image, SPOTS_PROMPT)
        return Reading(tuple(parse_places(text)), self._places_model, seconds, cost)

    async def roads(self, image: bytes, mime: str, places: list[ReadPlace]) -> Reading[ReadRoad]:
        del mime
        listed = "\n".join(
            f"{n}. {p.name} ({p.kind}) at [{p.point[0]}, {p.point[1]}]"
            for n, p in enumerate(places, start=1)
        )
        prompt = ROADS_PROMPT.format(places=listed)
        text, seconds, cost = await self._ask(self._roads_model, image, prompt)
        return Reading(tuple(parse_roads(text, len(places))), self._roads_model, seconds, cost)
