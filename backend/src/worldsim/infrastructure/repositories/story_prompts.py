"""Prompt additions (tables ``story_prompts`` and ``character_image_prompt``, 0053)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.story_prompts import CharacterImagePrompt, StoryPrompts


class SqlAlchemyStoryPromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, world_id: UUID) -> StoryPrompts:
        """The story's additions; a story that never set any has empty ones."""
        row = (
            await self._session.execute(
                text(
                    "SELECT llm_prefix, llm_suffix, image_prefix, image_suffix, version "
                    "FROM story_prompts WHERE world_id = :w"
                ),
                {"w": world_id},
            )
        ).first()
        if row is None:
            return StoryPrompts(world_id=world_id)
        return StoryPrompts(
            world_id=world_id,
            llm_prefix=row[0],
            llm_suffix=row[1],
            image_prefix=row[2],
            image_suffix=row[3],
            version=row[4],
        )

    async def save(self, prompts: StoryPrompts, expected_version: int) -> StoryPrompts:
        values = {**prompts.model_dump(exclude={"version"}), "next": expected_version + 1}
        if expected_version == 0:
            done = await self._session.execute(
                text(
                    "INSERT INTO story_prompts (world_id, llm_prefix, llm_suffix, image_prefix, "
                    "image_suffix, version) VALUES (:world_id, :llm_prefix, :llm_suffix, "
                    ":image_prefix, :image_suffix, :next) ON CONFLICT (world_id) DO NOTHING"
                ),
                values,
            )
        else:
            done = await self._session.execute(
                text(
                    "UPDATE story_prompts SET llm_prefix = :llm_prefix, llm_suffix = :llm_suffix, "
                    "image_prefix = :image_prefix, image_suffix = :image_suffix, "
                    "version = :next WHERE world_id = :world_id AND version = :expected"
                ),
                {**values, "expected": expected_version},
            )
        if getattr(done, "rowcount", 0) != 1:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT,
                f"story prompts for {prompts.world_id} changed elsewhere",
            )
        return prompts.model_copy(update={"version": expected_version + 1})

    async def characters(self, world_id: UUID) -> dict[UUID, CharacterImagePrompt]:
        rows = await self._session.execute(
            text(
                "SELECT character_id, prefix, suffix FROM character_image_prompt "
                "WHERE world_id = :w"
            ),
            {"w": world_id},
        )
        return {
            row[0]: CharacterImagePrompt(
                character_id=row[0], world_id=world_id, prefix=row[1], suffix=row[2]
            )
            for row in rows
        }

    async def save_character(self, prompt: CharacterImagePrompt) -> None:
        await self._session.execute(
            text(
                "INSERT INTO character_image_prompt (character_id, world_id, prefix, suffix) "
                "VALUES (:character_id, :world_id, :prefix, :suffix) "
                "ON CONFLICT (character_id) DO UPDATE SET prefix = EXCLUDED.prefix, "
                "suffix = EXCLUDED.suffix"
            ),
            prompt.model_dump(),
        )
