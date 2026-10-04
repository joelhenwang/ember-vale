"""Typed narrowing for untyped JSON values (provider bodies, JSONB rows).

``isinstance(value, dict)`` narrows to ``dict[Unknown, Unknown]`` under
strict checking, so every read after it is untyped. These helpers return
JSON objects and arrays with their real key and element types.
"""

from __future__ import annotations

from typing import Any, cast


def json_object(value: object) -> dict[str, Any] | None:
    """The value as a JSON object, or None when it is anything else."""
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def json_list(value: object) -> list[Any] | None:
    """The value as a JSON array, or None when it is anything else."""
    return cast(list[Any], value) if isinstance(value, list) else None
