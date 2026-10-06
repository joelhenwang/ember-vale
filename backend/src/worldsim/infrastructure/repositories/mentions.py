"""Cached place spans per line (table ``place_mention``, migration 0049)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def text_hash(line: str) -> str:
    """Matches ``encode(sha256(convert_to(line, 'UTF8')), 'hex')`` in SQL."""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


#: Lines worth reading: what characters said, tried and meant to do, and
#: what rumours are about. Newest intents first, so live stories go first.
_UNREAD = """
SELECT line FROM (
    SELECT DISTINCT ON (h) line, h, at FROM (
        SELECT coalesce(intent->'action'->>'topic', intent->'action'->>'attempt') AS line,
               created_at AS at
        FROM character_intent WHERE family IN ('communicate', 'interact')
        UNION ALL
        SELECT text, updated_at FROM character_intention
        UNION ALL
        SELECT purpose, NULL FROM narrative_hook
    ) s
    CROSS JOIN LATERAL (SELECT encode(sha256(convert_to(s.line, 'UTF8')), 'hex') AS h) x
    WHERE btrim(coalesce(s.line, '')) <> '' AND length(s.line) <= 4000
      AND NOT EXISTS (
        SELECT 1 FROM place_mention m WHERE m.text_hash = x.h AND m.model = :model
      )
    ORDER BY h, at DESC NULLS LAST
) u
ORDER BY at DESC NULLS LAST
LIMIT :limit
"""


class SqlAlchemyMentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def unread(self, model: str, limit: int) -> list[str]:
        """Lines with no cached spans under ``model`` yet."""
        rows = await self._session.execute(text(_UNREAD), {"model": model, "limit": limit})
        return [str(row.line) for row in rows]

    async def store(
        self, model: str, lines: Sequence[str], places: Sequence[Sequence[str]]
    ) -> None:
        for line, found in zip(lines, places, strict=True):
            await self._session.execute(
                text(
                    "INSERT INTO place_mention (text_hash, model, places) "
                    "VALUES (:h, :m, CAST(:p AS jsonb)) ON CONFLICT DO NOTHING"
                ),
                {"h": text_hash(line), "m": model, "p": json.dumps(list(found))},
            )

    async def places_for(self, model: str, lines: Sequence[str]) -> dict[str, list[str]]:
        """Cached place spans for the lines that have been read."""
        if not lines:
            return {}
        by_hash = {text_hash(line): line for line in lines}
        rows = await self._session.execute(
            text(
                "SELECT text_hash, places FROM place_mention "
                "WHERE model = :m AND text_hash = ANY(:hs)"
            ),
            {"m": model, "hs": list(by_hash)},
        )
        found: dict[str, list[str]] = {}
        for row in rows:
            spans: object = row.places
            if isinstance(spans, list):
                found[by_hash[row.text_hash]] = [str(span) for span in cast("list[object]", spans)]
        return found
