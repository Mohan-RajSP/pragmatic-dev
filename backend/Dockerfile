# syntax=docker/dockerfile:1

# ---- Base image with uv ----
FROM python:3.12-slim AS base

# uv: fast Python package manager (copied from the official image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# ---- Install dependencies (cached layer) ----
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev

# ---- Copy application code ----
COPY app ./app
# README.md is referenced by pyproject (`readme = ...`), so hatchling needs it
# when the project itself is installed below.
COPY README.md ./
RUN uv sync --no-dev

EXPOSE 8000

# Use the project's virtualenv created by uv
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

