"""Provider selection for the composition root (owned by S3-PROV-001).

Settings choose the profile; this module builds the per-role
gateways. No call site branches on provider: everything downstream
sees the ModelGateway port. The Stage 0 scripted path stays fake;
only the Stage 1 role set follows the active profile.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import replace

import httpx
from pydantic import SecretStr

from worldsim.application.ports.model_gateway import ModelGateway, ModelProfile
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.settings import AdapterKind, ProviderConnection, ProviderProfileRevision
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.hedge import HedgedGateway
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
    VENICE_CHAT_PROFILE,
)
from worldsim.infrastructure.model_gateway.retry import RetryingGateway
from worldsim.infrastructure.model_gateway.venice import VeniceGateway
from worldsim.infrastructure.settings import MODEL_ROLES, Settings

ROLE_NAMES = MODEL_ROLES

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
    provider = settings.provider
    if provider.active_profile in ("openrouter", "venice"):
        venice = provider.active_profile == "venice"
        key = provider.venice_api_key if venice else provider.openrouter_api_key
        assert key is not None, "settings reject a live profile without credentials"
        base_url = provider.venice_base_url if venice else provider.openrouter_base_url
        adapter = VeniceGateway if venice else OpenRouterGateway
        chat_profile = VENICE_CHAT_PROFILE if venice else OPENROUTER_CHAT_PROFILE
        overrides = provider.role_models
        profiles = {
            role: chat_profile.model_copy(
                update={"model_id": overrides.get(role, provider.default_model())}
            )
            for role in ROLE_NAMES
        }
        gateways: dict[str, ModelGateway] = {
            role: RetryingGateway(
                hedged(
                    adapter(
                        profiles[role],
                        api_key=key,
                        base_url=base_url,
                        client=client,
                        reasoning=provider.reasoning_for(role),
                        sort=None if venice else provider.openrouter_sort,
                    ),
                    hedge_after(role, provider.hedge_after_s, provider.role_hedge_after_s),
                )
            )
            for role in ROLE_NAMES
        }
        return gateways, profiles
    return (
        {
            role: FakeGateway(profile=FAKE_PROFILES[role], default_text=STAGE0_DEFAULT_BEAT)
            for role in ROLE_NAMES
        },
        dict(FAKE_PROFILES),
    )


#: Per-role hedge waits. Live calls one at a time answer in ~1 s (p90
#: ~2 s, scripts/routing_eval.py), but in play 9-12% of decisions,
#: reactions and director calls took over 4 s and 3-5% over 10 s. Roles
#: that write more (narrator, resolver) normally take longer. Day-end
#: summaries and digests (the summary role) run in the background: a twin
#: buys no felt speed, only a second bill (by call durations ~36% of them
#: fired one), so they are not hedged.
ROLE_HEDGE_AFTER_S: dict[str, float] = {
    "character": 4.0,
    "reaction": 4.0,
    "director": 5.0,
    "resolver": 7.0,
    "narrator": 7.0,
    "summary": 0.0,
}


def hedge_after(
    role: str, configured: float | None, per_role: Mapping[str, float] | None = None
) -> float:
    """Seconds before a twin request for this role; 0 means never.

    A per-role setting wins, then the global one, then ROLE_HEDGE_AFTER_S.
    """
    if per_role and role in per_role:
        return per_role[role]
    if configured is not None:
        return configured
    return ROLE_HEDGE_AFTER_S.get(role, 10.0)


def hedged(gateway: ModelGateway, after_s: float) -> ModelGateway:
    """A live gateway with slow-call hedging, unless it is switched off."""
    return HedgedGateway(gateway, after_s=after_s) if after_s > 0 else gateway


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
    elif connection.adapter == AdapterKind.VENICE:
        base = VENICE_CHAT_PROFILE
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
    reasoning: str | None = None,
    hedge_after_s: float | None = None,
) -> ModelGateway:
    """Runtime gateway for a pinned revision; never mutates shared state.

    OpenRouter pins build a fresh adapter from the connection endpoint
    and credential reference, through the same handling as environment
    selection. Fake pins copy the environment gateway scripted behavior
    under the pinned profile, so scripted tests keep working while the
    executed model comes from the pin. Reasoning is an environment
    setting, so pinned stories get the same level as unpinned ones.
    """
    profile = profile_for_pin(role, pin, connection)
    if connection.adapter in (AdapterKind.OPENROUTER, AdapterKind.VENICE):
        raw = (connection.credential_env or "").strip()
        secret = os.environ.get(raw) if raw else None
        if not secret:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                f"pinned provider {connection.name!r} has no credential configured",
                {"connection_id": str(connection.id)},
            )
        adapter = VeniceGateway if connection.adapter == AdapterKind.VENICE else OpenRouterGateway
        return RetryingGateway(
            hedged(
                adapter(
                    profile,
                    api_key=SecretStr(secret),
                    base_url=connection.endpoint,
                    client=client,
                    reasoning=reasoning,
                ),
                hedge_after_s if hedge_after_s is not None else hedge_after(role, None),
            )
        )
    if isinstance(env_gateway, FakeGateway):
        return replace(env_gateway, profile=profile)
    return FakeGateway(profile=profile, default_text=STAGE0_DEFAULT_BEAT)
