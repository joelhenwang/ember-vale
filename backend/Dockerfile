# Production API image (owned by S5-HARD-001).
#
# Build from the repo root so `backend/` and `content/` stay aligned:
#   docker build -f backend/Dockerfile -t worldsim-api .
# Run with the database URL, seed content, and (for non-loopback binds)
# the public-bind key; see compose.yaml and .env.example.
# The entrypoint runs from /app so relative content paths resolve
# exactly like a repo-root checkout. The root .dockerignore allow-lists
# the build context (docs/evidence/perf-infra-001).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.3

# Dependencies first, from the lock alone: a code change reuses this layer.
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project backend --frozen --no-dev --no-install-project

COPY backend/src ./backend/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --project backend --frozen --no-dev
COPY backend/migrations ./backend/migrations
COPY backend/prompts ./backend/prompts
COPY backend/alembic.ini ./backend/alembic.ini
COPY content ./content

EXPOSE 8000
# The venv is on PATH: no `uv run` at start (it re-resolved the project on
# every container start).
ENTRYPOINT ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && exec python -m worldsim.interfaces.cli serve"]
