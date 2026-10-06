"""Typed application settings (owned by S0-CONFIG-001).

Environment layout (prefix ``WORLDSIM_``, nested delimiter ``__``)::

    WORLDSIM_APP__ENVIRONMENT=test
    WORLDSIM_APP__HOST=127.0.0.1
    WORLDSIM_DATABASE__URL=postgresql+asyncpg://...
    WORLDSIM_PROVIDER__ACTIVE_PROFILE=fake
    WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=false
"""

from __future__ import annotations

import importlib.metadata
import sys
from typing import Literal, cast
from urllib.parse import urlparse

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import worldsim

Environment = Literal["local", "test"]
ProviderProfile = Literal["fake", "openrouter", "venice"]
#: Model-calling roles; selection.ROLE_NAMES re-exports this tuple.
MODEL_ROLES = ("character", "reaction", "resolver", "narrator", "director", "summary")
#: Hidden-reasoning budget sent to reasoning-capable models. "off" disables
#: thinking; the others map to OpenRouter's reasoning effort levels.
ReasoningLevel = Literal["off", "minimal", "low", "medium", "high"]

_PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::", ""})


class ApplicationSettings(BaseModel):
    """Process identity and HTTP bind contract."""

    environment: Environment = "local"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False


class DatabaseSettings(BaseModel):
    """PostgreSQL connection contract (S0-DB-001 owns engine/session)."""

    url: str = "postgresql+asyncpg://worldsim:changeme-local-only@localhost:5432/worldsim"
    pool_size: int = Field(default=5, ge=1, le=50)
    statement_timeout_ms: int = Field(default=5000, ge=100, le=60000)

    @field_validator("url")
    @classmethod
    def _require_postgres_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme.startswith("postgresql"):
            raise ValueError(
                "invalid database URL scheme; set WORLDSIM_DATABASE__URL to a "
                "postgresql:// or postgresql+asyncpg:// URL"
            )
        if not parsed.hostname or not parsed.path.strip("/"):
            raise ValueError(
                "invalid database URL; WORLDSIM_DATABASE__URL must include host and database name"
            )
        return value


class ProviderSettings(BaseModel):
    """Model gateway profile selection (adapters owned by S0-MODEL-001)."""

    active_profile: ProviderProfile = "fake"
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openrouter/auto"
    #: Venice (OpenAI-compatible): WORLDSIM_PROVIDER__ACTIVE_PROFILE=venice.
    venice_api_key: SecretStr | None = None
    venice_base_url: str = "https://api.venice.ai/api/v1"
    venice_model: str = "venice-uncensored-1-2"
    #: Optional per-role model overrides, e.g.
    #: WORLDSIM_PROVIDER__ROLE_MODELS__NARRATOR=mistralai/mistral-nemo.
    #: Roles left out use the active provider's model. Story pins still win.
    role_models: dict[str, str] = Field(default_factory=dict)
    #: Reasoning for every role (WORLDSIM_PROVIDER__REASONING=off), with
    #: optional per-role overrides (WORLDSIM_PROVIDER__ROLE_REASONING__RESOLVER=low).
    #: Unset leaves the model's own default, which for hybrid models such
    #: as DeepSeek V4 means thinking on every call.
    reasoning: ReasoningLevel | None = None
    role_reasoning: dict[str, ReasoningLevel] = Field(default_factory=dict)
    embedding_model: str = "test-embed"
    embedding_dim: int = Field(default=768, ge=1, le=4096)

    @field_validator("role_models")
    @classmethod
    def _known_roles_only(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = {role.lower(): model.strip() for role, model in value.items()}
        unknown = sorted(set(normalized) - set(MODEL_ROLES))
        if unknown:
            raise ValueError(
                f"unknown role(s) in WORLDSIM_PROVIDER__ROLE_MODELS: {unknown}; "
                f"expected any of {list(MODEL_ROLES)}"
            )
        empty = sorted(role for role, model in normalized.items() if not model)
        if empty:
            raise ValueError(f"empty model id for role(s) {empty} in role_models")
        return normalized

    @field_validator("role_reasoning", mode="before")
    @classmethod
    def _known_reasoning_roles(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized = {
            str(role).lower(): str(level).strip().lower()
            for role, level in cast("dict[object, object]", value).items()
        }
        unknown = sorted(set(normalized) - set(MODEL_ROLES))
        if unknown:
            raise ValueError(
                f"unknown role(s) in WORLDSIM_PROVIDER__ROLE_REASONING: {unknown}; "
                f"expected any of {list(MODEL_ROLES)}"
            )
        return normalized

    def reasoning_for(self, role: str) -> ReasoningLevel | None:
        """Reasoning level for one role: its override, else the global level."""
        if role in self.role_reasoning:
            return self.role_reasoning[role]
        return self.reasoning

    @field_validator("openrouter_base_url", "venice_base_url")
    @classmethod
    def _require_http_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(
                "invalid provider base URL; set WORLDSIM_PROVIDER__OPENROUTER_BASE_URL "
                "or WORLDSIM_PROVIDER__VENICE_BASE_URL to an http(s) URL"
            )
        return value

    def default_model(self) -> str:
        """The active provider's model for roles without an override."""
        if self.active_profile == "venice":
            return self.venice_model
        return self.openrouter_model


class TracingSettings(BaseModel):
    """LangSmith development tracing (durable audit owned by S0-TRACE-001)."""

    langsmith_enabled: bool = False
    langsmith_api_key: SecretStr | None = None
    project: str = "worldsim-local"
    endpoint: str = "https://api.smith.langchain.com"


class GraphSettings(BaseModel):
    """LangGraph checkpoint contract (owned by S1-GRAPH-001)."""

    checkpoint_schema: str = Field(default="graph_state", min_length=1, max_length=63)


class AutoplaySettings(BaseModel):
    """Background runner for server-side autoplay (E5 observatory).

    WORLDSIM_AUTOPLAY__ENABLED=false keeps the process from advancing any
    story on its own; Play then has no effect until a runner is enabled.
    """

    enabled: bool = True
    poll_seconds: float = Field(default=1.0, gt=0, le=60)


class SecuritySettings(BaseModel):
    """Explicit override for non-loopback listeners."""

    public_bind_allow: bool = False
    api_key: SecretStr | None = None


class Settings(BaseSettings):
    """Root settings; validated once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="WORLDSIM_", env_nested_delimiter="__", extra="forbid"
    )

    app: ApplicationSettings = ApplicationSettings()
    database: DatabaseSettings = DatabaseSettings()
    provider: ProviderSettings = ProviderSettings()
    tracing: TracingSettings = TracingSettings()
    graphs: GraphSettings = GraphSettings()
    security: SecuritySettings = SecuritySettings()
    autoplay: AutoplaySettings = AutoplaySettings()

    @model_validator(mode="after")
    def _reject_unsafe_combinations(self) -> Settings:
        if self.app.host in _PUBLIC_BIND_HOSTS and not (
            self.security.public_bind_allow
            and self.security.api_key is not None
            and self.security.api_key.get_secret_value()
        ):
            raise ValueError(
                "public bind refused: serving on "
                f"{self.app.host!r} requires WORLDSIM_SECURITY__PUBLIC_BIND_ALLOW=true "
                "and a non-empty WORLDSIM_SECURITY__API_KEY"
            )
        if self.provider.active_profile == "openrouter" and (
            self.provider.openrouter_api_key is None
            or not self.provider.openrouter_api_key.get_secret_value()
        ):
            raise ValueError(
                "openrouter profile selected without credentials: set "
                "WORLDSIM_PROVIDER__OPENROUTER_API_KEY or use the fake profile"
            )
        if self.provider.active_profile == "venice" and (
            self.provider.venice_api_key is None
            or not self.provider.venice_api_key.get_secret_value()
        ):
            raise ValueError(
                "venice profile selected without credentials: set "
                "WORLDSIM_PROVIDER__VENICE_API_KEY or use the fake profile"
            )
        return self


def get_settings() -> Settings:
    """Build and validate settings from the environment."""
    return Settings()


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def dependency_report(active: Settings | None = None) -> dict[str, str]:
    """Version/profile report for diagnostics (never includes secrets)."""
    current = active if active is not None else Settings()
    return {
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "worldsim_version": worldsim.__version__,
        "pydantic_version": _package_version("pydantic"),
        "pydantic_settings_version": _package_version("pydantic-settings"),
        "environment": current.app.environment,
        "active_profile": current.provider.active_profile,
    }
