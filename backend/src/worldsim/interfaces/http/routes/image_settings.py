"""Image generation settings: the service's status and catalog, and previews.

The drawing choices themselves are image preferences (PATCH
/settings/preferences, section ``images``); the runner reads them for
every job. A preview draws with unsaved choices so they can be tried
before saving; nothing it makes is stored.
"""

from __future__ import annotations

import base64
import io
from hashlib import sha256

from fastapi import APIRouter, Request
from PIL import Image

from worldsim.application.images import image_request
from worldsim.application.ports.images import GeneratedImage, ImageGenerationError
from worldsim.domain.assets import AssetKind
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.settings import IMAGE_RATIOS, IMAGE_STEPS, ImagePrefs
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.settings import OPERATOR

router = APIRouter(tags=["settings"])

#: Previews are for looking at, not keeping: sent back small.
PREVIEW_SIDE = 768


@router.get("/settings/images/service", response_model=api.ImageServiceView)
async def image_service(request: Request) -> api.ImageServiceView:
    state = request.app.state.app_state
    provider = state.settings.images.provider
    generator = state.images()
    if generator is None:
        return api.ImageServiceView(provider=provider, configured=False)
    catalog = await generator.catalog()
    return api.ImageServiceView(
        provider=provider,
        configured=True,
        reachable=catalog.reachable,
        loaded=catalog.loaded,
        checkpoint=catalog.checkpoint,
        queued=catalog.queued,
        checkpoints=catalog.checkpoints,
        styles=[api.ImageStyleView(id=s.id, label=s.label) for s in catalog.styles],
        ratios=list(IMAGE_RATIOS),
        steps=list(IMAGE_STEPS),
        error=catalog.error,
    )


@router.post("/settings/images/preview", response_model=api.ImagePreviewView)
async def image_preview(body: api.ImagePreviewRequest, request: Request) -> api.ImagePreviewView:
    state = request.app.state.app_state
    generator = state.images()
    if generator is None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "no image service: set WORLDSIM_IMAGES__PROVIDER=krea and KREA_BASE_URL",
        )
    if body.ratio not in IMAGE_RATIOS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"ratio must be one of {IMAGE_RATIOS}")
    if body.images is None:
        async with state.uow_factory()() as uow:
            prefs = (await uow.settings.get_preferences(OPERATOR)).images
    else:
        try:
            prefs = ImagePrefs.model_validate(body.images)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid images: {exc}") from exc
    # "Stable" previews follow the prompt, so the same words redraw the same set.
    base_seed = int.from_bytes(sha256(body.prompt.encode()).digest()[:4]) % 2**31
    images: list[api.ImagePreviewItem] = []
    for n in range(body.count):
        # Each picture of a set gets the next seed.
        shifted = prefs.model_copy(update={"seed": (prefs.seed + n) % 2**31})
        draw = image_request(
            body.prompt, body.ratio, AssetKind.MAP, shifted, stable_seed=(base_seed + n) % 2**31
        )
        try:
            made = await generator.generate(draw)
        except ImageGenerationError as exc:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, f"image service: {exc}") from exc
        images.append(_preview(made))
    return api.ImagePreviewView(images=images)


def _preview(image: GeneratedImage) -> api.ImagePreviewItem:
    """A small WebP data URL; bytes the server cannot read are sent as they are."""
    data, mime = image.data, image.mime
    try:
        with Image.open(io.BytesIO(image.data)) as source:
            picture = source.convert("RGB")
        picture.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        picture.save(out, format="WEBP", quality=88)
        data, mime = out.getvalue(), "image/webp"
    except (OSError, ValueError):
        pass
    return api.ImagePreviewItem(
        data_url=f"data:{mime};base64,{base64.b64encode(data).decode()}",
        seed=image.seed,
        width=image.width,
        height=image.height,
        seconds=image.seconds,
    )
