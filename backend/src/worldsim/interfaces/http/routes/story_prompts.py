"""Story settings: the player's words around this story's prompts.

Storyteller additions wrap every model prompt of the story's turns from
the next turn on; image additions wrap every image prompt (portraits,
places, scene pictures) from the next picture on; a character's image
additions wrap what is drawn of them.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.pictures import newest_asset
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.story_prompts import CharacterImagePrompt, StoryPrompts
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role

router = APIRouter(tags=["stories"])


async def _view(uow: UnitOfWork, world_id: UUID) -> api.StoryPromptsView:
    story = await uow.story_prompts.get(world_id)
    people = await uow.story_prompts.characters(world_id)
    characters: list[api.CharacterPromptView] = []
    for character in sorted(await uow.characters.list_for_world(world_id), key=lambda c: c.name):
        mine = people.get(character.id)
        portrait = await newest_asset(uow, world_id, AssetKind.PORTRAIT, character.id)
        characters.append(
            api.CharacterPromptView(
                character_id=character.id,
                name=character.name,
                prefix=mine.prefix if mine else "",
                suffix=mine.suffix if mine else "",
                portrait_asset_id=portrait.id if portrait else None,
            )
        )
    return api.StoryPromptsView(
        world_id=world_id,
        llm_prefix=story.llm_prefix,
        llm_suffix=story.llm_suffix,
        image_prefix=story.image_prefix,
        image_suffix=story.image_suffix,
        version=story.version,
        characters=characters,
    )


@router.get("/stories/{world_id}/prompts", response_model=api.StoryPromptsView)
async def read_story_prompts(world_id: UUID, request: Request) -> api.StoryPromptsView:
    await effective_role(request, world_id)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.worlds.get(world_id)
        return await _view(uow, world_id)


@router.put("/stories/{world_id}/prompts", response_model=api.StoryPromptsView)
async def save_story_prompts(
    world_id: UUID, body: api.StoryPromptsUpdate, request: Request
) -> api.StoryPromptsView:
    await effective_role(request, world_id)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.worlds.get(world_id)
        cast = {c.id for c in await uow.characters.list_for_world(world_id)}
        strangers = [str(c.character_id) for c in body.characters if c.character_id not in cast]
        if strangers:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, f"characters not in this story: {strangers}"
            )
        await uow.story_prompts.save(
            StoryPrompts(
                world_id=world_id,
                llm_prefix=body.llm_prefix.strip(),
                llm_suffix=body.llm_suffix.strip(),
                image_prefix=body.image_prefix.strip(),
                image_suffix=body.image_suffix.strip(),
            ),
            body.expected_version,
        )
        for character in body.characters:
            await uow.story_prompts.save_character(
                CharacterImagePrompt(
                    character_id=character.character_id,
                    world_id=world_id,
                    prefix=character.prefix.strip(),
                    suffix=character.suffix.strip(),
                )
            )
        await uow.commit()
        return await _view(uow, world_id)
