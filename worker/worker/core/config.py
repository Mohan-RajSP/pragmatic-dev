"""Worker configuration via environment variables (pydantic-settings).

The worker is a self-contained service — it does not import backend code. It
shares only two contracts with the backend: the Redis keys for tips and the
Celery task name (see `.github/PLAN.md`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor the .env path to the worker package root (this file lives at
# worker/worker/core/config.py, so parents[2] == worker/). This makes settings
# load correctly regardless of the current working directory the process is
# launched from.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Strongly-typed worker settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "pragmatic-dev-worker"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # --- Celery ---
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # --- Tips generation ---
    tips_list_key: str = "tips:list"
    tips_trigger_key: str = "tips:trigger"
    # Records the most recent "skipped generation" event so the backend SSE
    # stream can relay it to clients (shared contract with the backend).
    tips_skip_event_key: str = "tips:skip:last"
    tips_max_items: int = 10
    tip_schedule_seconds: float = 300.0
    # Beat-scheduled messages expire if not executed in time (prevents backlog
    # build-up during an outage — a newer tick supersedes stale ones).
    tip_task_expires: int = 270

    # Mutual exclusion: only one generation runs at a time (distributed lock).
    tips_lock_key: str = "tips:generation:lock"
    tips_lock_ttl: int = 120  # seconds; auto-expires if a worker dies mid-task

    # Single retry chain: a marker prevents a fresh task from starting a second,
    # parallel retry chain while an earlier failure is still retrying.
    tips_retry_marker_key: str = "tips:retry:in_progress"
    tip_retry_marker_buffer: int = 30  # marker TTL = countdown + this buffer

    # Exponential retry backoff for transient LLM/network failures.
    tip_max_retries: int = 3         # hard cap on retry attempts
    tip_retry_base_delay: int = 10   # seconds (first retry)
    tip_retry_max_delay: int = 600   # cap on the backoff

    # --- LLM ---
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.8
    openai_api_key: str | None = None

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def effective_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single source of truth)."""
    return Settings()






