"""Shared adapter failures (owned by S0-UOW-001)."""

from __future__ import annotations

from uuid import UUID

from worldsim.domain.errors import DomainError, ErrorCode


def unique_violation(exc: BaseException, constraint: str) -> bool:
    """True when exc is an integrity failure on the named unique constraint.

    psycopg surfaces the name via ``orig.diag``; asyncpg (the runtime
    engine driver) exposes ``constraint_name`` directly on the driver
    error, one extra nesting level down. Walk both before concluding.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        direct = getattr(current, "constraint_name", None)
        if direct == constraint:
            return True
        name = getattr(getattr(current, "diag", None), "constraint_name", None)
        if name == constraint:
            return True
        nxt: BaseException | None = None
        for attr in ("orig", "__cause__", "__context__"):
            candidate = getattr(current, attr, None)
            if isinstance(candidate, BaseException) and id(candidate) not in seen:
                nxt = candidate
                break
        current = nxt
    return False


def missing(kind: str, identity: UUID) -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, f"unknown {kind}: {identity}")


def version_conflict(kind: str, identity: UUID, expected: int, actual: int) -> DomainError:
    return DomainError(
        ErrorCode.VERSION_CONFLICT,
        f"stale {kind} {identity}: expected={expected} actual={actual}",
        {"kind": kind, "id": str(identity), "expected": expected, "actual": actual},
    )
