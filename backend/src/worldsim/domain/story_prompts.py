"""The player's own words added to a story's prompts.

Per story: a prefix and suffix for every storyteller (LLM) prompt, and
for every image prompt. Per character: a prefix and suffix for images
of them (their portrait, and scene pictures they are in), such as
"always wears a red scarf". Empty means nothing is added.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: Long enough for a paragraph of guidance; the image service reads
#: 512 tokens of prompt in all, so image additions are kept shorter.
LLM_ADDITION_CHARS = 2000
IMAGE_ADDITION_CHARS = 400


class StoryPrompts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    world_id: UUID
    llm_prefix: str = Field(default="", max_length=LLM_ADDITION_CHARS)
    llm_suffix: str = Field(default="", max_length=LLM_ADDITION_CHARS)
    image_prefix: str = Field(default="", max_length=IMAGE_ADDITION_CHARS)
    image_suffix: str = Field(default="", max_length=IMAGE_ADDITION_CHARS)
    version: int = Field(default=0, ge=0)


class CharacterImagePrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    character_id: UUID
    world_id: UUID
    prefix: str = Field(default="", max_length=IMAGE_ADDITION_CHARS)
    suffix: str = Field(default="", max_length=IMAGE_ADDITION_CHARS)


def framed(prefix: str, text: str, suffix: str, joiner: str = " ") -> str:
    """``text`` with the additions around it; empty additions add nothing."""
    return joiner.join(part for part in (prefix.strip(), text, suffix.strip()) if part)
