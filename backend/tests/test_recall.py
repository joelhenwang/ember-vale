"""Recall by relevance: local embeddings lift what bears on the moment."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import uuid
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_stage1_api import MIGRATIONS, SEED_DIR, ApiClient, _advance, _route_for, _seed_two

from worldsim.application.orchestration.stage1 import (
    _recall_focus,  # pyright: ignore[reportPrivateUsage]
)
from worldsim.application.ports.local_models import (
    Embeddings,
    EmbedKind,
    LocalModelsUnavailable,
    Span,
)
from worldsim.domain.characters import Character
from worldsim.domain.context import SourceCandidate
from worldsim.domain.enums import Visibility
from worldsim.domain.memory import recall_text, relevance
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.local_models.client import BACKOFF_S, LocalModelsClient
from worldsim.infrastructure.local_models.indexer import RecallIndexer
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app
from worldsim.interfaces.http.state import AppState, build_state

DIM = 512


def _bag_of_words(sentence: str) -> list[float]:
    """Deterministic stand-in embedding: shared words mean high cosine."""
    vector = [0.0] * DIM
    for word in re.findall(r"[a-z]+", sentence.lower()):
        if len(word) > 3:
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeLocalModels:
    def __init__(self) -> None:
        self.calls: list[tuple[EmbedKind, list[str]]] = []
        self.down = False
        self.model = "fake-bow"

    async def embed(self, texts: list[str], kind: EmbedKind) -> Embeddings:
        if self.down:
            raise LocalModelsUnavailable("off")
        self.calls.append((kind, list(texts)))
        return Embeddings(vectors=[_bag_of_words(t) for t in texts], model=self.model)

    async def extract(
        self, texts: list[str], labels: dict[str, str], threshold: float = 0.5
    ) -> list[list[Span]]:
        return [[] for _ in texts]


def test_relevance_maps_cosine_onto_zero_to_one() -> None:
    assert relevance(0.1) == 0.0
    assert relevance(0.45) == 0.0
    assert relevance(0.625) == pytest.approx(0.5)
    assert relevance(0.9) == 1.0


def test_recall_text_drops_keys_from_prose_lines() -> None:
    assert recall_text("reply:communicate", "Marta replies") == "Marta replies"
    assert recall_text("weather", "rain") == "weather: rain"
    assert recall_text(None, "Wren remembers the mill") == "Wren remembers the mill"


def test_recall_focus_says_where_with_whom_and_what_for() -> None:
    wren = Character(
        id=uuid.uuid4(),
        world_id=uuid.uuid4(),
        name="Wren",
        card_version=1,
        location_id=uuid.uuid4(),
        stamina=80,
        mana=40,
    )
    focus = _recall_focus(
        wren, "Market", ["Ash"], "find the purse", ["silver locket"], ["Ash says hello"]
    )
    assert focus == (
        "Wren is at Market. With Ash. Means to: find the purse "
        "Carrying silver locket. Ash says hello"
    )


def test_client_backs_off_after_a_failure() -> None:
    now = [100.0]
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        if len(hits) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"vectors": [[1.0, 0.0]], "model": "m"})

    client = LocalModelsClient(
        "http://models.test", clock=lambda: now[0], transport=httpx.MockTransport(handler)
    )
    with pytest.raises(LocalModelsUnavailable):
        asyncio.run(client.embed(["a"], "query"))
    with pytest.raises(LocalModelsUnavailable, match="backing off"):
        asyncio.run(client.embed(["a"], "query"))
    assert hits == ["/embed"]  # the second call never left the process
    now[0] += BACKOFF_S + 1
    found = asyncio.run(client.embed(["a"], "query"))
    assert found.vectors == [[1.0, 0.0]] and found.model == "m"


def test_client_reads_extracted_spans_in_text_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["labels"] == {"place": "somewhere"}
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "place": [{"text": "mill", "start": 20, "end": 24, "confidence": 0.9}],
                        "person": [{"text": "Wren", "start": 0, "end": 4, "confidence": 0.8}],
                    }
                ],
                "model": "g",
                "ms": 1,
            },
        )

    client = LocalModelsClient("http://models.test", transport=httpx.MockTransport(handler))
    spans = asyncio.run(client.extract(["Wren walks to the old mill"], {"place": "somewhere"}))
    assert [(s.label, s.text) for s in spans[0]] == [("person", "Wren"), ("place", "mill")]


async def _add_memory(world: uuid.UUID, owner: uuid.UUID, words: str, phase: int) -> str:
    memory_id = uuid.uuid4()
    engine = create_engine(Settings())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO recent_memory (id, world_id, owner_character_id, text, "
                    "visibility, created_phase_index, salience) "
                    "VALUES (:id, :w, :o, :t, 'private', :p, 1.0)"
                ),
                {"id": memory_id, "w": world, "o": owner, "t": words, "p": phase},
            )
    finally:
        await engine.dispose()
    return f"mem:{memory_id}"


@pytest.fixture
def recall_app(
    migrated_db: None,
) -> Iterator[tuple[ApiClient, FakeGateway, FakeLocalModels, TestClient]]:
    gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
    models = FakeLocalModels()
    app = create_app(
        Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS, gateway_factory=lambda: gateway
    )
    app.state.app_state._local_models = models  # pyright: ignore[reportPrivateUsage]
    with TestClient(app) as raw:
        yield ApiClient(raw), gateway, models, raw


def _state(models: FakeLocalModels) -> AppState:
    state = build_state(Settings(), seed_dir=SEED_DIR, migrations_dir=MIGRATIONS)
    state._local_models = models  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    return state


def _memory(owner: uuid.UUID, source_id: str, words: str, phase: int) -> SourceCandidate:
    return SourceCandidate(
        source_id=source_id,
        data_class="memories",
        visibility=Visibility.PRIVATE,
        owner_id=owner,
        text=words,
        score=1.0,
        created_phase_index=phase,
    )


def test_indexer_then_recall_lifts_the_relevant_and_brings_back_the_old(
    migrated_db: None,
) -> None:
    models = FakeLocalModels()
    ids = asyncio.run(_seed_two())
    world, wren = ids["world"], ids["wren"]
    locket_old = asyncio.run(_add_memory(world, wren, "The silver locket lies under the mill", 1))
    bread_old = asyncio.run(_add_memory(world, wren, "Fresh bread smells wonderful", 2))
    locket_new = asyncio.run(
        _add_memory(world, wren, "Nessa asked about the silver locket under the mill", 20)
    )
    weather_new = asyncio.run(_add_memory(world, wren, "Clouds gather over the hills", 20))

    async def scenario() -> list[SourceCandidate]:
        state = _state(models)
        try:
            indexer = RecallIndexer(state.uow_factory(), models, batch=64)
            stored = 0
            while (count := await indexer.run_once()) > 0:
                stored += count
            assert stored >= 4
            assert await indexer.run_once() == 0  # nothing left to index
            return await state.stage1()._recall_by_relevance(  # pyright: ignore[reportPrivateUsage]
                wren,
                [
                    _memory(
                        wren, locket_new, "Nessa asked about the silver locket under the mill", 20
                    ),
                    _memory(wren, weather_new, "Clouds gather over the hills", 20),
                ],
                "Wren wants the silver locket under the mill",
                since=10,
                now_index=21,
                half_life=40,
                weight=0.6,
            )
        finally:
            await state.engine.dispose()

    lifted = asyncio.run(scenario())
    scores = {c.source_id: c.score for c in lifted}
    assert scores[locket_new] > scores[weather_new] == 1.0
    assert locket_old in scores  # older than the window, yet on point: back
    assert bread_old not in scores  # older and beside the point: stays out
    returned = next(c for c in lifted if c.source_id == locket_old)
    assert returned.text.startswith("Day 1, ") and "silver locket" in returned.text


def test_indexer_reindexes_when_the_service_changes_model(migrated_db: None) -> None:
    models = FakeLocalModels()
    ids = asyncio.run(_seed_two())
    asyncio.run(_add_memory(ids["world"], ids["wren"], "The mill wheel creaks", 1))

    async def drain(indexer: RecallIndexer) -> int:
        stored = 0
        while (count := await indexer.run_once()) > 0:
            stored += count
        return stored

    async def scenario() -> tuple[int, int]:
        state = _state(models)
        try:
            indexer = RecallIndexer(state.uow_factory(), models, batch=64)
            first = await drain(indexer)
            models.model = "fake-bow-r2"  # the service restarted with fixed output
            return first, await drain(indexer)
        finally:
            await state.engine.dispose()

    first, second = asyncio.run(scenario())
    assert first >= 1
    assert second == first  # everything again, under the new name


def test_recall_is_skipped_when_the_service_is_off(migrated_db: None) -> None:
    models = FakeLocalModels()
    models.down = True
    keep = _memory(uuid.uuid4(), "mem:x", "anything", 0)

    async def scenario() -> list[SourceCandidate]:
        state = _state(models)
        try:
            return await state.stage1()._recall_by_relevance(  # pyright: ignore[reportPrivateUsage]
                uuid.uuid4(), [keep], "focus", since=0, now_index=1, half_life=40, weight=0.6
            )
        finally:
            await state.engine.dispose()

    assert asyncio.run(scenario()) == [keep]


def test_decisions_ask_for_recall_with_the_moment(
    recall_app: tuple[ApiClient, FakeGateway, FakeLocalModels, TestClient],
) -> None:
    client, gateway, models, _raw = recall_app
    ids = asyncio.run(_seed_two())
    gateway.route = _route_for(ids, {})
    assert _advance(client, ids["world"], 1).status_code == 200
    queries = [texts[0] for kind, texts in models.calls if kind == "query"]
    assert any(q.startswith("Wren is at Hearth.") for q in queries)
    assert any(q.startswith("Ash is at Market.") for q in queries)
