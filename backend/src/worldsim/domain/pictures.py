"""Scene pictures: a painted moment of a scene, with the people in it.

A picture is asked for at a key moment (a turning point picked out of
the narration, arriving somewhere new, a first meeting, a rumour
settled) or by the player ("Paint this scene"). Its
image is an ordinary image job of kind ``scene``; this record says what
to paint and how to caption it in the story.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PictureMoment(StrEnum):
    ARRIVAL = "arrival"
    MEETING = "meeting"
    SETTLED = "settled"
    #: Picked out of the narration: a discovery, a confrontation, a reveal.
    TURNING = "turning"
    MANUAL = "manual"


#: The image service takes at most three reference images per picture;
#: one is kept for the place's own art.
MAX_PICTURE_CHARACTERS = 2
#: Key-moment pictures are at least this many beats apart (the image
#: machine paints one in ~16 s; turns take 3-9 s).
MOMENT_COOLDOWN_BEATS = 3


class ScenePicture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    scene_id: UUID
    job_id: UUID
    moment: PictureMoment
    #: A short headline ("A bell beneath the tide"); older pictures have none.
    title: str | None = Field(default=None, max_length=80)
    #: Shown under the picture in the story.
    caption: str = Field(min_length=1, max_length=400)
    #: The words to paint from, when the player wrote or edited them.
    prompt: str | None = Field(default=None, max_length=2000)
    #: Who keeps their face in the picture (registered references).
    character_ids: list[UUID] = Field(default_factory=list, max_length=MAX_PICTURE_CHARACTERS)
    location_id: UUID | None = None
    created_phase_index: int = Field(default=0, ge=0)
