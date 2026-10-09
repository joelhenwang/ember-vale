"""Composition root for the HTTP boundary (owned by S0-API-001).

``AppState`` carries everything handlers need: settings, engine, seed
content, and factories for the gateway and external exporter. Routes
stay thin; services own rules.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

import worldsim
from worldsim.application.orchestration.background import BackgroundNarration
from worldsim.application.orchestration.stage1 import Stage1Orchestrator
from worldsim.application.ports.map_reader import MapReader
from worldsim.application.ports.model_gateway import ModelGateway
from worldsim.application.ports.traces import TraceExporter
from worldsim.application.ports.writer import Writer
from worldsim.application.queries.presentation import JourneyCache
from worldsim.application.settings.resolution import PinnedRuntime
from worldsim.application.tasks.service import TaskService
from worldsim.application.tracing.service import TraceService
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.rules.dnd import DataTables, load_data
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.geography.openrouter import OpenRouterMapReader
from worldsim.infrastructure.images.krea import KreaImageGenerator
from worldsim.infrastructure.local_models.client import LocalModelsClient
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import (
    STAGE0_DEFAULT_BEAT,
    STAGE0_SCRIPTED_PROFILE,
)
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings
from worldsim.infrastructure.tracing.langsmith import select_exporter
from worldsim.infrastructure.writing.openrouter import OpenRouterWriter

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
SEED_DIR = _REPO_ROOT / "content" / "seeds" / "stage0"
DND_DATA_DIR = _REPO_ROOT / "content" / "dnd"


_dnd_tables: DataTables | None = None


def dnd_tables() -> DataTables:
    """Vendored SRD tables, loaded once per process."""
    global _dnd_tables
    if _dnd_tables is None:
        _dnd_tables = load_data(DND_DATA_DIR)
    return _dnd_tables


def stage0_gateway() -> FakeGateway:
    return FakeGateway(profile=STAGE0_SCRIPTED_PROFILE, default_text=STAGE0_DEFAULT_BEAT)


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    seed_dir: Path
    migrations_dir: Path
    gateway_factory: Callable[[], FakeGateway]
    exporter: TraceExporter
    #: One client per process so its failure back-off is shared.
    _local_models: LocalModelsClient | None = None
    #: Narration still running after its beat returned, per story.
    narration: BackgroundNarration | None = None
    #: The image service client (Krea), when images are switched on.
    _images: KreaImageGenerator | None = None
    _map_reader: MapReader | None = None
    _writer: Writer | None = None
    #: Renown counts per (story, player, newest event), shared by requests.
    journeys: JourneyCache = field(default_factory=JourneyCache)

    def uow_factory(self) -> Callable[[], SqlAlchemyUnitOfWork]:
        engine = self.engine

        def _factory() -> SqlAlchemyUnitOfWork:
            return create_unit_of_work(engine)

        return _factory

    def tasks(self) -> TaskService:
        return TaskService(self.uow_factory())

    def traces(self) -> TraceService:
        return TraceService(self.uow_factory(), self.exporter)

    def stage1(self) -> Stage1Orchestrator:
        """Stage 1 orchestrator with per-role gateways for the active profile."""
        from worldsim.infrastructure.model_gateway.selection import (
            gateway_for_pin,
            gateways_for_settings,
            hedge_after,
        )

        factory = self.uow_factory()
        override = self.gateway_factory if self.gateway_factory is not stage0_gateway else None
        gateways, profiles = gateways_for_settings(self.settings, override)

        def _for_role(role: str) -> ModelGateway:
            return gateways[role]

        def _for_pin(role: str, pin: PinnedRuntime) -> ModelGateway:
            return gateway_for_pin(
                role,
                pin.profile,
                pin.connection,
                env_gateway=gateways[role],
                reasoning=self.settings.provider.reasoning_for(role),
                hedge_after_s=hedge_after(
                    role,
                    self.settings.provider.hedge_after_s,
                    self.settings.provider.role_hedge_after_s,
                ),
            )

        return Stage1Orchestrator(
            factory,
            CanonicalTransaction(factory),
            TaskService(factory),
            TraceService(factory, self.exporter),
            _for_role,
            profiles,
            pin_gateway_factory=_for_pin,
            local_models=self.local_models(),
            narration=self.narration,
            paint_moments=self.images() is not None,
            # Reads key moments (only when painting) and suggests a joining
            # companion's calling (callings-001).
            moment_writer=self.writer(),
            max_parallel_calls=self.settings.app.parallel_model_calls,
            reacting_bystanders=self.settings.app.reacting_bystanders,
            xp_scale=self.settings.app.xp_scale,
        )

    def local_models(self) -> LocalModelsClient | None:
        """The local model service client, when one is configured."""
        if self._local_models is None and self.settings.local_models.url:
            local = self.settings.local_models
            self._local_models = LocalModelsClient(local.url, timeout_s=local.timeout_s)
        return self._local_models

    def images(self) -> KreaImageGenerator | None:
        """The image service client, when WORLDSIM_IMAGES__PROVIDER=krea."""
        images = self.settings.images
        if self._images is None and images.provider == "krea" and images.krea_base_url:
            self._images = KreaImageGenerator(images.krea_base_url, timeout_s=images.krea_timeout_s)
        return self._images

    def map_reader(self) -> MapReader | None:
        """The map reader, when an OpenRouter key is configured."""
        if self._map_reader is None:
            key = self.settings.provider.openrouter_api_key
            if key is not None and key.get_secret_value().strip():
                maps = self.settings.maps
                self._map_reader = OpenRouterMapReader(
                    key.get_secret_value().strip(),
                    self.settings.provider.openrouter_base_url,
                    maps.places_model,
                    maps.roads_model,
                    reasoning=maps.reasoning,
                    max_tokens=maps.max_tokens,
                    timeout_s=maps.timeout_s,
                )
                self._map_reader.use_terrain_model(maps.terrain_model)
        return self._map_reader

    def writer(self) -> Writer | None:
        """The library writing helper, when an OpenRouter key is configured."""
        if self._writer is None:
            key = self.settings.provider.openrouter_api_key
            if key is not None and key.get_secret_value().strip():
                writing = self.settings.writing
                self._writer = OpenRouterWriter(
                    key.get_secret_value().strip(),
                    self.settings.provider.openrouter_base_url,
                    writing.model,
                    reasoning=writing.reasoning,
                    max_tokens=writing.max_tokens,
                    timeout_s=writing.timeout_s,
                )
        return self._writer


MIGRATIONS_DIR = Path("backend/migrations")


def build_state(
    settings: Settings,
    *,
    seed_dir: Path = SEED_DIR,
    migrations_dir: Path = MIGRATIONS_DIR,
    gateway_factory: Callable[[], FakeGateway] = stage0_gateway,
) -> AppState:
    exporter: TraceExporter = select_exporter(
        settings.tracing,
        environment=settings.app.environment,
        app_version=worldsim.__version__,
    )
    return AppState(
        narration=BackgroundNarration() if settings.app.background_narration else None,
        settings=settings,
        engine=create_engine(settings),
        seed_dir=seed_dir,
        migrations_dir=migrations_dir,
        gateway_factory=gateway_factory,
        exporter=exporter,
    )
