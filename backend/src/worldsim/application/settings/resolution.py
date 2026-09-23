"""Pinned provider resolution per story (owned by MAINMENU-A05).

A story's setup snapshot may pin a provider profile revision. Resolution
reads that pin once per phase run; every retry inside the run reuses the
same revision, and another story's edits cannot bleed in. No pin means the
process environment settings apply, exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.settings import ProviderConnection, ProviderProfileRevision


@dataclass(frozen=True)
class SamplingParams:
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int = 512
    model_id: str | None = None
    profile_id: str | None = None
    profile_revision: int | None = None


async def resolve_profile(uow: UnitOfWork, world_id: UUID) -> ProviderProfileRevision | None:
    """The story's pinned profile revision, or None for environment defaults.

    A setup that names a pin must resolve: an unparsable reference
    or a missing revision raises instead of silently falling back,
    so broken explicit pins fail closed before any generation.
    """
    try:
        setup = await uow.stories.get_setup(world_id)
    except DomainError:
        return None
    payload: Any = setup.payload
    if not isinstance(payload, dict):
        return None
    # Created snapshots nest DraftAi under "art" (stories.create); "ai" never exists there.
    section = cast(dict[str, Any], payload).get("art")
    if not isinstance(section, dict):
        return None
    options = cast(dict[str, Any], section)
    profile_id = options.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        return None
    try:
        profile_uuid = UUID(profile_id)
        revision_int = int(options.get("profile_revision", 1))
    except (ValueError, TypeError):
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            f"story pins an invalid provider profile reference {profile_id!r}",
            {"profile_id": profile_id},
        ) from None
    try:
        return await uow.settings.get_profile(profile_uuid, revision_int)
    except DomainError:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            f"story pins unknown provider profile {profile_uuid} revision {revision_int}",
            {
                "profile_id": str(profile_uuid),
                "profile_revision": revision_int,
            },
        ) from None


def sampling_from_pin(pin: PinnedRuntime) -> SamplingParams:
    """Sampling values for one pinned revision."""
    profile = pin.profile
    return SamplingParams(
        temperature=profile.temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        max_tokens=profile.max_tokens,
        model_id=profile.model_id,
        profile_id=str(profile.id),
        profile_revision=profile.revision,
    )


@dataclass(frozen=True)
class PinnedRuntime:
    """A story pin: revision plus the connection it executes through.

    The connection carries the adapter, endpoint, and credential
    reference the runtime gateway is built from; the revision carries
    the pinned model and sampling. Neither follows the profile head.
    """

    profile: ProviderProfileRevision
    connection: ProviderConnection


async def resolve_pin(uow: UnitOfWork, world_id: UUID) -> PinnedRuntime | None:
    """Pinned runtime for one story, or None for environment defaults.

    Only a story with no pin configured falls back. A resolved
    revision whose connection is unavailable raises instead, so a
    broken explicit pin never silently becomes environment execution.
    """
    profile = await resolve_profile(uow, world_id)
    if profile is None:
        return None
    try:
        connection = await uow.settings.get_connection(profile.connection_id)
    except DomainError:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            f"story pins provider profile {profile.id} whose connection "
            "{profile.connection_id} is unavailable",
            {
                "profile_id": str(profile.id),
                "profile_revision": profile.revision,
                "connection_id": str(profile.connection_id),
            },
        ) from None
    return PinnedRuntime(profile=profile, connection=connection)


async def resolve_sampling(uow: UnitOfWork, world_id: UUID) -> SamplingParams:
    """Effective sampling for one phase run, captured once at admission."""
    pin = await resolve_pin(uow, world_id)
    if pin is None:
        return SamplingParams()
    return sampling_from_pin(pin)
