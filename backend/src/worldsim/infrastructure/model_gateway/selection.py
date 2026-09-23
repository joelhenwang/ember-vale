"""Provider selection for the composition root (owned by S3-PROV-001).

Settings choose the profile; this module builds the per-role
gateways. No call site branches on provider: everything downstream
sees the ModelGateway port. The Stage 0 scripted path stays fake;
only the Stage 1 role set follows the active profile.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace

import httpx
from pydantic import SecretStr

from worldsim.application.ports.model_gateway import ModelGateway, ModelProfile
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.settings import AdapterKind, ProviderConnection, ProviderProfileRevision
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import (
    CHARACTER_FAKE_PROFILE,
    DIRECTOR_FAKE_PROFILE,
    NARRATOR_FAKE_PROFILE,
    OPENROUTER_CHAT_PROFILE,
    REACTION_FAKE_PROFILE,
    RESOLVER_FAKE_PROFILE,
    STAGE0_DEFAULT_BEAT,
    SUMMARY_FAKE_PROFILE,
)
from worldsim.infrastructure.model_gateway.retry import RetryingGateway
from worldsim.infrastructure.settings import Settings

ROLE_NAMES = ("character", "reaction", "resolver", "narrator", "director", "summary")

FAKE_PROFILES: dict[str, ModelProfile] = {
    "character": CHARACTER_FAKE_PROFILE,
    "reaction": REACTION_FAKE_PROFILE,
    "resolver": RESOLVER_FAKE_PROFILE,
    "narrator": NARRATOR_FAKE_PROFILE,
    "director": DIRECTOR_FAKE_PROFILE,
    "summary": SUMMARY_FAKE_PROFILE,
}


def gateways_for_settings(
    settings: Settings,
    fake_factory: Callable[[], FakeGateway] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, ModelGateway], dict[str, ModelProfile]]:
    """Per-role gateways and profiles for the active provider selection.

    An injected fake factory (tests scripting model behavior) wins over
    the fake profile; the live profile never consults it. An injected
    HTTP client (tests intercepting the adapter transport) is shared by
    every live gateway built here.
    """
    if fake_factory is not None and settings.provider.active_profile == "fake":
        return (
            {role: fake_factory() for role in ROLE_NAMES},
            dict(FAKE_PROFILES),
        )
    if settings.provider.active_profile == "openrouter":
        key = settings.provider.openrouter_api_key
        assert key is not None, "settings reject openrouter without credentials"
        profile = OPENROUTER_CHAT_PROFILE.model_copy(
            update={"model_id": settings.provider.openrouter_model}
        )
        gateways: dict[str, ModelGateway] = {
            role: RetryingGateway(
                OpenRouterGateway(
                    profile,
                    api_key=key,
                    base_url=settings.provider.openrouter_base_url,
                    client=client,
                )
            )
            for role in ROLE_NAMES
        }
        profiles = {role: profile for role in ROLE_NAMES}
        return gateways, profiles
    return (
        {
            role: FakeGateway(profile=FAKE_PROFILES[role], default_text=STAGE0_DEFAULT_BEAT)
            for role in ROLE_NAMES
        },
        dict(FAKE_PROFILES),
    )


def profile_for_pin(
    role: str, pin: ProviderProfileRevision, connection: ProviderConnection
) -> ModelProfile:
    """Per-role execution profile for a pinned revision.

    Role context windows and capabilities stay exactly as configured
    for the environment; only the adapter, model, and version tag come
    from the pin, so audit rows name what actually executed. The version
    tag carries the pinned profile identity, never the moving head.
    """
    if connection.adapter == AdapterKind.OPENROUTER:
        base = OPENROUTER_CHAT_PROFILE
    else:
        base = FAKE_PROFILES[role]
    return base.model_copy(
        update={
            "adapter": connection.adapter.value,
            "model_id": pin.model_id,
            "version": f"pin-{pin.id.hex[:8]}-r{pin.revision}",
        }
    )


def gateway_for_pin(
    role: str,
    pin: ProviderProfileRevision,
    connection: ProviderConnection,
    *,
    env_gateway: ModelGateway | None = None,
    client: httpx.AsyncClient | None = None,
) -> ModelGateway:
    """Runtime gateway for a pinned revision; never mutates shared state.

    OpenRouter pins build a fresh adapter from the connection endpoint
    and credential reference, through the same handling as environment
    selection. Fake pins copy the environment gateway scripted behavior
    under the pinned profile, so scripted tests keep working while the
    executed model comes from the pin.
    """
    profile = profile_for_pin(role, pin, connection)
    if connection.adapter == AdapterKind.OPENROUTER:
        raw = (connection.credential_env or "").strip()
        secret = os.environ.get(raw) if raw else None
        if not secret:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"pinned provider {connection.name!r} has no credential configured",
                {"connection_id": str(connection.id)},
            )
        return RetryingGateway(
            OpenRouterGateway(
                profile,
                api_key=SecretStr(secret),
                base_url=connection.endpoint,
                client=client,
            )
        )
    if isinstance(env_gateway, FakeGateway):
        return replace(env_gateway, profile=profile)
    return FakeGateway(profile=profile, default_text=STAGE0_DEFAULT_BEAT)
