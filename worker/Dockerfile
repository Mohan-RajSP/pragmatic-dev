# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies (cached layer)
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev

# Copy application code
COPY worker ./worker
# README.md is referenced by pyproject (`readme = ...`); hatchling needs it
# when the project itself is installed below.
COPY README.md ./
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Default: run the Celery worker. docker-compose overrides the command for Beat.
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]

