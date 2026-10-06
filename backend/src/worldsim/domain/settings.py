"""Provider connections, pinned profile revisions, and operator preferences.

Secrets never live here: a connection names an environment variable, and
reads report only whether that variable is currently set. Profile revisions
carry nonsecret model IDs plus supported sampling values; stories pin a
revision so later edits cannot bleed into running worlds.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from worldsim.domain.time import utcnow

SUPPORTED_SAMPLING = ("temperature", "top_p", "top_k")
#: The single operator whose preferences a local install reads.
LOCAL_OPERATOR = "local"


class AdapterKind(StrEnum):
    FAKE = "fake"
    OPENROUTER = "openrouter"
    VENICE = "venice"


class ProviderConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    adapter: AdapterKind
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=512)
    credential_env: str | None = Field(default=None, max_length=128)
    allow_local_endpoint: bool = False
    config_version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow)


class ProviderProfileRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    connection_id: UUID
    revision: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=100)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    capabilities: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class GameplayDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pacing: str = Field(default="measured", max_length=32)
    autoplay_dwell: str = Field(default="normal", max_length=16)


class AccessibilityPrefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    font_scale: int = Field(default=100, ge=75, le=200)
    motion: str = Field(default="system", max_length=16)


class LocalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(default="Storyteller", max_length=64)
    avatar: str = Field(default="J", max_length=8)


#: Aspect ratios the image service draws (krea2-studio docs/API.md).
IMAGE_RATIOS = ("1:1", "16:9", "9:16", "3:2", "2:3", "4:3", "3:4")
ImageRatio = Literal["1:1", "16:9", "9:16", "3:2", "2:3", "4:3", "3:4"]
#: Sampling steps the service accepts.
IMAGE_STEPS = (4, 6, 8, 10, 12, 16, 20)


class ImagePrefs(BaseModel):
    """How portraits and place art are drawn (Krea 2 Studio fields).

    Read by the image runner for every job, so a change applies to the
    next picture without a restart. ``None`` leaves a field to the service
    or, for ratios, to the style pack.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Off leaves new jobs queued (nothing is drawn) until switched back on.
    enabled: bool = True
    #: Shared by everyone using the service: switching costs ~30-35 s once.
    checkpoint: str | None = Field(default="krea2Anime_v15_bf16", max_length=128)
    mode: Literal["draft", "fast", "full"] = "fast"
    #: stable: one seed per subject (a retry redraws the same picture).
    seed_mode: Literal["stable", "random", "fixed"] = "stable"
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    #: The detail LoRA (snofs); a strength other than 1.0 costs ~+4 s.
    detail: bool = True
    detail_scale: float = Field(default=1.0, ge=0.0, le=2.0)
    #: The 4-step Turbo LoRA; off is ~2x slower (8 steps by default).
    turbo: bool = True
    steps: int | None = Field(default=None)
    #: Style LoRA for painted packs; None draws without one.
    style: str | None = Field(default="kreanima-lora-r32", max_length=128)
    style_scale: float = Field(default=1.0, ge=0.0, le=2.0)
    portrait_ratio: ImageRatio | None = None
    place_ratio: ImageRatio | None = None
    scene_ratio: ImageRatio | None = None
    #: Paint key moments (arrivals, first meetings, settled rumours) by itself.
    scene_moments: bool = True

    @field_validator("steps")
    @classmethod
    def _known_steps(cls, steps: int | None) -> int | None:
        if steps is not None and steps not in IMAGE_STEPS:
            raise ValueError(f"steps must be one of {IMAGE_STEPS}")
        return steps


class ApplicationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operator: str = Field(default="local", min_length=1, max_length=64)
    gameplay: GameplayDefaults = Field(default_factory=GameplayDefaults)
    accessibility: AccessibilityPrefs = Field(default_factory=AccessibilityPrefs)
    profile: LocalProfile = Field(default_factory=LocalProfile)
    images: ImagePrefs = Field(default_factory=ImagePrefs)
    version: int = Field(default=0, ge=0)
