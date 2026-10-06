"""Long-term memory: salience scoring and digest promotion (owned by S3-MEM-001).

Salience is persisted per perception row and bumped by code when a
daily summary cites the row; recency decay applies at query time so
old rows fade unless promoted. Promotion compresses qualifying old
rows into a digest that re-enters assembly with a fixed high score.
Raw rows are never rewritten: digests cite source IDs, and content
hashes let the audit prove sources are unmodified.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: Salience of a fresh row; citation bumps add up to the cap.
BASE_SALIENCE = 1.0
MAX_SALIENCE = 5.0

#: World-config keys with their defaults. Weights live in config so
#: tuning never needs a migration.
HALF_LIFE_PHASES_KEY = "memory.salience.half_life_phases"
DEFAULT_HALF_LIFE_PHASES = 40
CITE_BUMP_KEY = "memory.salience.cite_bump"
DEFAULT_CITE_BUMP = 1.0
RECENT_PHASES_KEY = "memory.retrieval.recent_phases"
DEFAULT_RECENT_PHASES = 30
SALIENCE_FLOOR_KEY = "memory.retrieval.salience_floor"
DEFAULT_SALIENCE_FLOOR = 2.0
PROMOTION_ENABLED_KEY = "memory.promotion.enabled"
PROMOTION_THRESHOLD_KEY = "memory.promotion.threshold"
DEFAULT_PROMOTION_THRESHOLD = 2.0
PROMOTION_MIN_AGE_KEY = "memory.promotion.min_age_phases"
DEFAULT_PROMOTION_MIN_AGE = 10
PROMOTION_MAX_PER_DAY_KEY = "memory.promotion.max_per_day"
DEFAULT_PROMOTION_MAX_PER_DAY = 1
PROMOTION_MAX_TOTAL_KEY = "memory.promotion.max_digests_per_owner"
DEFAULT_PROMOTION_MAX_TOTAL = 8

#: Fixed assembly score for digests: above memories, below identity.
DIGEST_SCORE = 2.5


def score_salience(base: float, age_phases: int, half_life_phases: int) -> float:
    """Persisted salience decayed by age; pure and deterministic."""
    if age_phases <= 0:
        return base
    return base * (0.5 ** (age_phases / max(1, half_life_phases)))


def content_hash(payload: Any) -> str:
    """Stable sha256 over canonical JSON for immutability audits."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class MemoryDigest(BaseModel):
    """Compressed record of promoted sources; sources stay immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    world_id: UUID
    owner_character_id: UUID
    text: str = Field(min_length=1, max_length=4000)
    source_ids: list[str] = Field(default_factory=list)
    day: int = Field(ge=1)
    created_phase_index: int = Field(ge=0)
    profile_version: str = Field(default="", max_length=64)
    prompt_version: str = Field(default="", max_length=64)
    version: int = Field(default=1, ge=1)


def observation_hash(facts: list[dict[str, str]]) -> str:
    """Canonical hash over key/value fact pairs; matches migration 0019."""
    return content_hash([{"key": fact["key"], "value": fact["value"]} for fact in facts])


def memory_hash(text: str) -> str:
    """Canonical hash over memory text; matches migration 0019."""
    return content_hash(text)


#: Recall by relevance. Similarity to "what is going on now" lifts an
#: observation or memory on top of its decayed salience, so what bears
#: on the moment wins a crowded budget, and an old row can come back.
RELEVANCE_WEIGHT_KEY = "memory.retrieval.relevance_weight"
DEFAULT_RELEVANCE_WEIGHT = 0.6
#: Cosine below LOW counts as unrelated, above HIGH as fully on point.
#: From embeddinggemma's spread on 80 real decisions (scripts/recall_eval.py,
#: 2026-10-06): p10 0.39, p50 0.63, p90 0.78.
RELEVANCE_LOW = 0.45
RELEVANCE_HIGH = 0.80
#: Rows older than the recent window come back only this close (top quarter).
RECALL_OLD_MIN_SIMILARITY = 0.70
RECALL_OLD_LIMIT = 4


class RecallSource(BaseModel):
    """One embeddable context source: an observation fact or a memory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=160)
    world_id: UUID
    owner_character_id: UUID
    created_phase_index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=2000)


def recall_text(key: str | None, value: str) -> str:
    """What gets embedded: the prose line, without its time label."""
    if key is None or key.startswith(("attempt:", "reply:")):
        return value
    return f"{key}: {value}"


def relevance(similarity: float) -> float:
    """Cosine similarity mapped onto 0..1."""
    span = RELEVANCE_HIGH - RELEVANCE_LOW
    return min(1.0, max(0.0, (similarity - RELEVANCE_LOW) / span))
