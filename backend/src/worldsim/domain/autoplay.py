"""Server-authoritative autoplay (E5 observatory).

One row per story says whether the world plays on its own. The runner
admits one beat at a time through the same execution gate as a manual
step, so autoplay, Step and a second tab can never run two beats at
once. Autoplay never runs unattended: an observer page reports presence,
and the runner pauses once nobody has been seen for the grace period.

The rules here are pure; the runner and routes only persist their
results.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.ids import WorldId

#: Pause once no observer has been seen for this long.
PRESENCE_GRACE_SECONDS = 60
#: Beats one Play press may run before autoplay pauses itself.
DEFAULT_BEAT_LIMIT = 10
MAX_BEAT_LIMIT = 100
#: Pause between one committed beat and admitting the next.
MAX_DELAY_SECONDS = 600
#: Retry delay when the slot is busy (a manual step is running).
BUSY_RETRY_SECONDS = 3


class AutoplayStatus(StrEnum):
    PLAYING = "playing"
    PAUSED = "paused"


class StopReason(StrEnum):
    """Why autoplay last paused; ``user`` when someone pressed Pause."""

    USER = "user"
    BEAT_LIMIT = "beat_limit"
    NO_OBSERVERS = "no_observers"
    ERROR = "error"
    ARCHIVED = "archived"


class AutoplayState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: WorldId
    status: AutoplayStatus = AutoplayStatus.PAUSED
    delay_seconds: int = Field(default=0, ge=0, le=MAX_DELAY_SECONDS)
    beats_left: int = Field(default=0, ge=0, le=MAX_BEAT_LIMIT)
    stop_reason: StopReason | None = None
    stop_detail: str | None = Field(default=None, max_length=500)
    last_seen_at: datetime | None = None
    next_due_at: datetime | None = None
    beats_run: int = Field(default=0, ge=0)
    version: int = Field(default=0, ge=0)


def paused_default(world_id: WorldId) -> AutoplayState:
    """State of a story that never played."""
    return AutoplayState(world_id=world_id)


def play(
    state: AutoplayState, *, now: datetime, delay_seconds: int, beat_limit: int
) -> AutoplayState:
    """Start (or retune) autoplay; the first beat is due immediately.

    Pressing Play counts as presence, so the grace period starts now.
    """
    return state.model_copy(
        update={
            "status": AutoplayStatus.PLAYING,
            "delay_seconds": delay_seconds,
            "beats_left": beat_limit,
            "stop_reason": None,
            "stop_detail": None,
            "last_seen_at": now,
            "next_due_at": now,
            "beats_run": 0,
        }
    )


def pause(state: AutoplayState, reason: StopReason, detail: str | None = None) -> AutoplayState:
    """Stop admitting beats; a beat already running finishes on its own."""
    return state.model_copy(
        update={
            "status": AutoplayStatus.PAUSED,
            "stop_reason": reason,
            "stop_detail": detail[:500] if detail else None,
            "next_due_at": None,
        }
    )


def seen(state: AutoplayState, now: datetime) -> AutoplayState:
    return state.model_copy(update={"last_seen_at": now})


def observers_gone(state: AutoplayState, now: datetime) -> bool:
    """True once nobody has reported presence within the grace period."""
    if state.last_seen_at is None:
        return True
    return now - state.last_seen_at > timedelta(seconds=PRESENCE_GRACE_SECONDS)


def is_due(state: AutoplayState, now: datetime) -> bool:
    return (
        state.status == AutoplayStatus.PLAYING
        and state.next_due_at is not None
        and state.next_due_at <= now
    )


def beat_committed(state: AutoplayState, now: datetime) -> AutoplayState:
    """Count a beat this runner committed; pause at the limit."""
    left = max(0, state.beats_left - 1)
    after = state.model_copy(update={"beats_left": left, "beats_run": state.beats_run + 1})
    if left == 0:
        return pause(after, StopReason.BEAT_LIMIT)
    return after.model_copy(update={"next_due_at": now + timedelta(seconds=state.delay_seconds)})


def retry_later(state: AutoplayState, now: datetime, seconds: int) -> AutoplayState:
    return state.model_copy(update={"next_due_at": now + timedelta(seconds=seconds)})
