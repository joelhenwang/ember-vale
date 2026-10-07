"""Writing help in the library studios: enhance an overview, fill empty fields.

Both ask a small text model on OpenRouter, so they cost a little: each
answer says how much. Fill never overwrites what the player wrote; the
answer only carries the fields that were empty.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from worldsim.application.library.writing import (
    Field,
    Place,
    WritingAnswerError,
    enhance_prompt,
    fill_prompt,
    parse_enhanced,
    parse_filled,
)
from worldsim.application.ports.writer import Writer, WritingError
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.interfaces.http import schemas as api

router = APIRouter(tags=["library"])


def _writer(request: Request) -> Writer:
    writer = request.app.state.app_state.writer()
    if writer is None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "no writer: set WORLDSIM_PROVIDER__OPENROUTER_API_KEY",
        )
    return writer


@router.post("/library/writing/enhance", response_model=api.WritingEnhanceView)
async def enhance(body: api.WritingEnhanceRequest, request: Request) -> api.WritingEnhanceView:
    try:
        written = await _writer(request).write(enhance_prompt(body.kind, body.overview, body.name))
        text = parse_enhanced(written.text)
    except (WritingError, WritingAnswerError) as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, str(exc)) from exc
    return api.WritingEnhanceView(
        text=text, model=written.model, seconds=written.seconds, cost_usd=written.cost_usd
    )


@router.post("/library/writing/fill", response_model=api.WritingFillView)
async def fill(body: api.WritingFillRequest, request: Request) -> api.WritingFillView:
    fields = [Field(f.key, f.label, f.hint, f.value, f.max_length) for f in body.fields]
    places = [Place(p.name, p.description) for p in body.places]
    kinds = [k.strip()[:40] for k in body.place_kinds if k.strip()]
    wants_places = body.add_places > 0 or any(not p.description.strip() for p in places)
    if not any(not f.value.strip() for f in fields) and not wants_places:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "every field is already filled")
    try:
        written = await _writer(request).write(
            fill_prompt(body.kind, body.overview, fields, body.name, places, body.add_places, kinds)
        )
        values, filled = parse_filled(written.text, fields, places, body.add_places, kinds)
    except (WritingError, WritingAnswerError) as exc:
        raise DomainError(ErrorCode.PRECONDITION_FAILED, str(exc)) from exc
    return api.WritingFillView(
        values=values,
        places=[
            api.WritingFilledPlace(name=p.name, description=p.description, new=p.new, kind=p.kind)
            for p in filled
        ],
        model=written.model,
        seconds=written.seconds,
        cost_usd=written.cost_usd,
    )
