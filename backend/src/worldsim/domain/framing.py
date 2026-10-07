"""Frames on a picture: which part of it a layout shows.

A frame is a rectangle in fractions of the picture's width and height
(x, y its top-left corner), so it survives resizing. A character's
imported picture keeps two: the portrait (2:3, cards and sheets) and the
face (square, round tokens and avatars), both on the original picture.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Rounding slack: frames come from a pointer on a scaled picture.
_SLACK = 1e-3


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside(self) -> Frame:
        if self.x + self.w > 1 + _SLACK or self.y + self.h > 1 + _SLACK:
            raise ValueError("a frame must lie inside its picture")
        return self

    def contains(self, other: Frame) -> bool:
        return (
            other.x >= self.x - _SLACK
            and other.y >= self.y - _SLACK
            and other.x + other.w <= self.x + self.w + _SLACK
            and other.y + other.h <= self.y + self.h + _SLACK
        )

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) on a picture of this size."""
        left, top = round(self.x * width), round(self.y * height)
        right = min(width, max(left + 1, round((self.x + self.w) * width)))
        bottom = min(height, max(top + 1, round((self.y + self.h) * height)))
        return left, top, right, bottom


class PictureFrames(BaseModel):
    """Where a character's portrait and face are on their imported picture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    portrait: Frame
    face: Frame

    @model_validator(mode="after")
    def _face_in_portrait(self) -> PictureFrames:
        if not self.portrait.contains(self.face):
            raise ValueError("the face must lie inside the portrait")
        return self


def within(outer: Frame, inner: Frame) -> Frame:
    """The inner frame in fractions of the outer one (e.g. the face on the
    portrait crop rather than on the whole picture)."""
    return Frame(
        x=min(1.0, max(0.0, (inner.x - outer.x) / outer.w)),
        y=min(1.0, max(0.0, (inner.y - outer.y) / outer.h)),
        w=min(1.0, inner.w / outer.w),
        h=min(1.0, inner.h / outer.h),
    )


#: Kept so a frame list in JSON reads [x, y, w, h].
FrameList = list[float]


def as_list(frame: Frame) -> FrameList:
    return [frame.x, frame.y, frame.w, frame.h]
