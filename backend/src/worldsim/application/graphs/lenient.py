"""Deterministic clean-up of model JSON before a repair round trip.

A schema repair costs a full extra model call (seconds on a live
provider). Two failure shapes carry no meaning and are fixed here:

- keys the schema does not have (a ``wait`` that lists every other
  action's fields as ``null``, or a stray ``"type": "json_object"``):
  dropped, but only when every validation error is such a key;
- version bookkeeping the model cannot know (``expected_versions``):
  filled from the server's own records by the caller.

Anything else still goes to the normal repair path.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

#: Validation errors quoted back to the model in a repair request.
REPAIR_DETAIL_ERRORS = 3


def _parse_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return None
    return cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else None


def _drop_at(document: Any, loc: tuple[int | str, ...]) -> bool:
    """Delete the key at ``loc``; union tags in the path are skipped."""
    node = document
    for part in loc[:-1]:
        if isinstance(node, dict) and part in node:
            node = cast("dict[Any, Any]", node)[part]
        elif isinstance(node, list) and isinstance(part, int):
            items = cast("list[Any]", node)
            if part >= len(items):
                return False
            node = items[part]
        # else: a discriminated-union tag, not a key in the document
    if isinstance(node, dict) and loc and loc[-1] in node:
        del cast("dict[Any, Any]", node)[loc[-1]]
        return True
    return False


def validate_lenient[T](adapter: TypeAdapter[T], raw: str) -> T:
    """Validate ``raw``; on extra-key-only failures, drop them and retry once."""
    try:
        return adapter.validate_json(raw)
    except ValidationError as exc:
        errors = exc.errors()
        if not errors or any(e["type"] != "extra_forbidden" for e in errors):
            raise
        document = _parse_object(raw)
        if document is None:
            raise
        dropped = [_drop_at(document, tuple(e["loc"])) for e in errors]
        if not all(dropped):
            raise
        return adapter.validate_python(document)


def unwrap_tagged(raw: str, tags: frozenset[str], field: str) -> str:
    """Flatten ``{"propose_hook": {...}}`` into ``{"action": "propose_hook", ...}``.

    Some models answer a tagged choice by nesting the payload under the
    tag instead of naming it in ``field``. Only an object with no
    ``field`` and exactly one key, a known tag holding an object, is
    rewritten; everything else passes through for normal validation.
    """
    document = _parse_object(raw)
    if document is None or field in document or len(document) != 1:
        return raw
    ((tag, payload),) = document.items()
    if tag not in tags or not isinstance(payload, dict):
        return raw
    return json.dumps({**cast("dict[str, Any]", payload), field: tag})


def normalize_tagged(raw: str, tags: frozenset[str], field: str, wrappers: frozenset[str]) -> str:
    """Bring common shape variants of a tagged object back to ``{field: tag, ...}``.

    Seen live from json-mode models (playtest-005): ``"type": "json_object"``
    echoed from the request, the tag under ``"type"`` instead of ``field``,
    and the payload nested under a wrapper key (``"proposal"``, ``"hook"``)
    or under the tag itself. Only those shapes are rewritten; anything
    else is left for validation and repair.
    """
    raw = unwrap_tagged(raw, tags, field)
    document = _parse_object(raw)
    if document is None:
        return raw
    changed = False
    if document.get("type") == "json_object":
        del document["type"]
        changed = True
    for alias in ("type", "response", "kind"):
        value = document.get(alias)
        if field not in document and isinstance(value, str) and value in tags:
            document[field] = document.pop(alias)
            changed = True
    for wrapper in wrappers:
        inner = document.get(wrapper)
        if isinstance(inner, dict):
            del document[wrapper]
            for key, value in cast("dict[str, Any]", inner).items():
                document.setdefault(key, value)
            changed = True
    if not changed:
        return raw
    return unwrap_tagged(json.dumps(document), tags, field)


def fill_expected_versions(raw: str, versions: Mapping[str, int]) -> str:
    """Set each effect's ``expected_versions`` from the server's versions.

    The resolver cannot know aggregate versions; the commit checks them
    against what the server read, so the server's values are the only
    correct ones. Ids the server has no version for are left as given.
    """
    document = _parse_object(raw)
    if document is None:
        return raw
    effects = document.get("effects")
    if not isinstance(effects, list):
        return raw
    for effect in cast("list[Any]", effects):
        if not isinstance(effect, dict):
            continue
        item = cast("dict[str, Any]", effect)
        affected = item.get("affected_ids")
        if not isinstance(affected, list):
            continue
        given = item.get("expected_versions")
        known: dict[str, Any] = (
            dict(cast("dict[str, Any]", given)) if isinstance(given, dict) else {}
        )
        for target in cast("list[Any]", affected):
            if str(target) in versions:
                known[str(target)] = versions[str(target)]
        item["expected_versions"] = known
    return json.dumps(document)


def repair_detail(exc: ValidationError) -> str:
    """Short, specific reasons for a repair request (field path: message)."""
    parts = [
        f"{'.'.join(str(p) for p in e['loc']) or 'root'}: {e['msg']}"
        for e in exc.errors()[:REPAIR_DETAIL_ERRORS]
    ]
    more = exc.error_count() - len(parts)
    suffix = f"; and {more} more" if more > 0 else ""
    return "; ".join(parts) + suffix
