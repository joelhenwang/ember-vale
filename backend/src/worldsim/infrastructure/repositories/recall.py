"""Embeddings for recall by relevance (table ``recall_vector``, migration 0048).

Plain SQL: the vector type is pgvector's, sent and read as text, so the
backend needs no pgvector client package.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.memory import RecallSource, recall_text


def _vector(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


class SqlAlchemyRecallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def unindexed(self, model: str, limit: int) -> list[RecallSource]:
        """Observation facts and memories with no vector under ``model`` yet."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT * FROM (
                        SELECT 'obs:' || o.id || ':' || (f->>'key') AS source_id,
                               o.world_id, o.observer_character_id AS owner,
                               o.created_phase_index, f->>'key' AS key, f->>'value' AS value
                        FROM observation o CROSS JOIN LATERAL jsonb_array_elements(o.facts) f
                        UNION ALL
                        SELECT 'mem:' || m.id, m.world_id, m.owner_character_id,
                               m.created_phase_index, NULL, m.text
                        FROM recent_memory m
                    ) s
                    WHERE btrim(coalesce(s.value, '')) <> ''
                      AND NOT EXISTS (
                        SELECT 1 FROM recall_vector r
                        WHERE r.source_id = s.source_id AND r.model = :model
                      )
                    LIMIT :limit
                    """
                ),
                {"model": model, "limit": limit},
            )
        ).all()
        return [
            RecallSource(
                source_id=row.source_id,
                world_id=row.world_id,
                owner_character_id=row.owner,
                created_phase_index=row.created_phase_index,
                text=recall_text(row.key, row.value)[:2000],
            )
            for row in rows
        ]

    async def store(
        self, model: str, sources: Sequence[RecallSource], vectors: Sequence[Sequence[float]]
    ) -> None:
        for source, vector in zip(sources, vectors, strict=True):
            await self._session.execute(
                text(
                    """
                    INSERT INTO recall_vector (source_id, model, world_id, owner_character_id,
                                               created_phase_index, text, embedding)
                    VALUES (:source_id, :model, :world_id, :owner, :phase, :text,
                            CAST(:embedding AS vector))
                    ON CONFLICT (source_id, model) DO NOTHING
                    """
                ),
                {
                    "source_id": source.source_id,
                    "model": model,
                    "world_id": source.world_id,
                    "owner": source.owner_character_id,
                    "phase": source.created_phase_index,
                    "text": source.text,
                    "embedding": _vector(vector),
                },
            )

    async def similarities(
        self, owner_id: UUID, model: str, query: Sequence[float], source_ids: Sequence[str]
    ) -> dict[str, float]:
        """Cosine similarity of each indexed source to the query."""
        if not source_ids:
            return {}
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT source_id, 1 - (embedding <=> CAST(:query AS vector)) AS similarity
                    FROM recall_vector
                    WHERE owner_character_id = :owner AND model = :model
                      AND source_id = ANY(:ids)
                    """
                ),
                {
                    "owner": owner_id,
                    "model": model,
                    "query": _vector(query),
                    "ids": list(source_ids),
                },
            )
        ).all()
        # An empty vector has no direction (NaN cosine): treat it as unindexed.
        return {
            row.source_id: float(row.similarity)
            for row in rows
            if math.isfinite(float(row.similarity))
        }

    async def nearest_before(
        self,
        owner_id: UUID,
        model: str,
        query: Sequence[float],
        before_phase_index: int,
        exclude: Sequence[str],
        min_similarity: float,
        limit: int,
    ) -> list[tuple[RecallSource, float]]:
        """The owner's closest rows older than ``before_phase_index``."""
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT source_id, world_id, owner_character_id, created_phase_index, text,
                           1 - (embedding <=> CAST(:query AS vector)) AS similarity
                    FROM recall_vector
                    WHERE owner_character_id = :owner AND model = :model
                      AND created_phase_index < :before
                      AND NOT (source_id = ANY(:exclude))
                    ORDER BY embedding <=> CAST(:query AS vector)
                    LIMIT :limit
                    """
                ),
                {
                    "owner": owner_id,
                    "model": model,
                    "query": _vector(query),
                    "before": before_phase_index,
                    "exclude": list(exclude),
                    "limit": limit,
                },
            )
        ).all()
        return [
            (
                RecallSource(
                    source_id=row.source_id,
                    world_id=row.world_id,
                    owner_character_id=row.owner_character_id,
                    created_phase_index=row.created_phase_index,
                    text=row.text,
                ),
                float(row.similarity),
            )
            for row in rows
            if float(row.similarity) >= min_similarity
        ]
