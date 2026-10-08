"""Paint this scene: a suggested prompt to edit, and queuing the picture.

Players may paint scenes they were in; watchers any scene. The picture
is painted in the background by the image runner and shows in the
story once ready (presentation ``scene_art``).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from worldsim.application.capabilities import is_omniscient, parse_role
from worldsim.application.images import image_additions, load_style_pack, world_style_pack
from worldsim.application.pictures import (
    newest_asset,
    queue_picture,
    repaint,
    scene_prompt,
    suggest,
)
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import AssetKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.pictures import PictureMoment, ScenePicture
from worldsim.domain.scenes import Scene
from worldsim.domain.story_prompts import framed
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role

router = APIRouter(tags=["pictures"])


async def _scene_for(
    uow: UnitOfWork, world_id: UUID, scene_id: UUID, viewer: UUID | None, omniscient: bool
) -> Scene:
    scene = await uow.scenes.get_scene(scene_id)
    if scene.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "scene is not in this world")
    if not omniscient and viewer not in {p.character_id for p in scene.participants}:
        raise DomainError(ErrorCode.FORBIDDEN, "you can only paint scenes you were in")
    return scene


@router.get("/world/scenes/{scene_id}/picture-suggestion", response_model=api.PictureSuggestion)
async def picture_suggestion(
    scene_id: UUID, world_id: UUID, request: Request
) -> api.PictureSuggestion:
    role, viewer = await effective_role(request, world_id)
    omniscient = is_omniscient(parse_role(role))
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await _scene_for(uow, world_id, scene_id, viewer, omniscient)
        offer = await suggest(uow, world_id, scene_id, viewer)
        people: list[api.PictureCharacter] = []
        for character_id in offer.character_ids:
            character = await uow.characters.get(character_id)
            portrait = await newest_asset(uow, world_id, AssetKind.PORTRAIT, character_id)
            people.append(
                api.PictureCharacter(
                    character_id=character_id, name=character.name, has_face=portrait is not None
                )
            )
        place = None
        if offer.location_id is not None:
            place = (await uow.locations.get(offer.location_id)).name
        added = await image_additions(uow, world_id, offer.character_ids)
    return api.PictureSuggestion(
        added_before=framed(added.story_prefix, added.people_prefix, ""),
        added_after=framed(added.people_suffix, added.story_suffix, ""),
        prompt=offer.prompt,
        caption=offer.caption,
        characters=people,
        place=place,
        available=state.images() is not None,
    )


@router.post("/world/scenes/{scene_id}/pictures", response_model=api.SceneArtView)
async def paint_scene(
    scene_id: UUID, body: api.PaintSceneRequest, request: Request
) -> api.SceneArtView:
    role, viewer = await effective_role(request, body.world_id)
    omniscient = is_omniscient(parse_role(role))
    state = request.app.state.app_state
    if state.images() is None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED, "no image machine is set up on this server"
        )
    async with state.uow_factory()() as uow:
        scene = await _scene_for(uow, body.world_id, scene_id, viewer, omniscient)
        offer = await suggest(uow, body.world_id, scene_id, viewer)
        index = (
            (await uow.events.get_event(scene.event_id)).absolute_index
            if scene.event_id is not None
            else 0
        )
        picture = await queue_picture(
            uow,
            body.world_id,
            scene_id,
            PictureMoment.MANUAL,
            body.caption or offer.caption,
            index=index,
            character_ids=offer.character_ids,
            location_id=offer.location_id,
            style_pack=await world_style_pack(uow, body.world_id),
            prompt=body.prompt.strip(),
        )
        if picture is None:  # manual keys are unique, so this cannot happen
            raise DomainError(ErrorCode.INVARIANT_VIOLATED, "picture was not queued")
        await uow.commit()
    return api.SceneArtView(
        picture_id=picture.id,
        scene_id=scene_id,
        moment=picture.moment.value,
        caption=picture.caption,
        status="pending",
        phase_index=picture.created_phase_index,
        location_id=picture.location_id,
    )


async def _picture_for(
    uow: UnitOfWork, world_id: UUID, picture_id: UUID, viewer: UUID | None, omniscient: bool
) -> ScenePicture:
    picture = await uow.pictures.get(picture_id)
    if picture.world_id != world_id:
        raise DomainError(ErrorCode.NOT_FOUND, "picture is not in this world")
    await _scene_for(uow, world_id, picture.scene_id, viewer, omniscient)
    return picture


async def _repainting(uow: UnitOfWork, picture: ScenePicture) -> bool:
    if picture.repaint_job_id is None:
        return False
    job = await uow.assets.get_job(picture.repaint_job_id)
    return job.status.value in ("pending", "running")


@router.get("/world/pictures/{picture_id}/prompt", response_model=api.PicturePromptView)
async def picture_prompt(
    picture_id: UUID, world_id: UUID, request: Request
) -> api.PicturePromptView:
    """The whole prompt the image service gets for this picture."""
    role, viewer = await effective_role(request, world_id)
    omniscient = is_omniscient(parse_role(role))
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        picture = await _picture_for(uow, world_id, picture_id, viewer, omniscient)
        job = await uow.assets.get_job(picture.job_id)
        pack = load_style_pack(
            state.seed_dir.parent.parent / "visual-styles", job.style_pack_version
        )
        prompt = await scene_prompt(uow, pack, picture)
        repainting = await _repainting(uow, picture)
    return api.PicturePromptView(
        prompt=prompt,
        edited=picture.raw_prompt,
        repainting=repainting,
        repaint_job_id=picture.repaint_job_id if repainting else None,
    )


@router.post("/world/pictures/{picture_id}/repaint", response_model=api.PicturePromptView)
async def repaint_picture(
    picture_id: UUID, body: api.RepaintRequest, request: Request
) -> api.PicturePromptView:
    """Paint the picture again from the player's whole prompt, sent as written."""
    role, viewer = await effective_role(request, body.world_id)
    omniscient = is_omniscient(parse_role(role))
    state = request.app.state.app_state
    if state.images() is None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED, "no image machine is set up on this server"
        )
    async with state.uow_factory()() as uow:
        picture = await _picture_for(uow, body.world_id, picture_id, viewer, omniscient)
        if await _repainting(uow, picture):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, "this picture is already being painted again"
            )
        job = await repaint(uow, picture, body.prompt, await world_style_pack(uow, body.world_id))
        await uow.commit()
    return api.PicturePromptView(
        prompt=body.prompt.strip(), edited=True, repainting=True, repaint_job_id=job.id
    )
