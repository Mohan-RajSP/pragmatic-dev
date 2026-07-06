"""Application configuration via environment variables.

Uses pydantic-settings so all config is validated and typed. Nothing is
hardcoded — every value can be overridden through the environment / `.env`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    # --- Application ---
    app_name: str = "pragmatic-dev-backend"
    environment: str = "development"
    log_level: str = "INFO"
    api_prefix: str = ""

    # --- CORS ---
    # `NoDecode` stops pydantic-settings from JSON-decoding the raw env value so
    # our validator can accept a plain comma-separated string (e.g. "*", or
    # "http://a,http://b").
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # --- Tips feature ---
    tips_list_key: str = "tips:list"
    tips_trigger_key: str = "tips:trigger"
    tips_max_items: int = 10
    tip_stream_poll_interval: float = 2.0
    sse_heartbeat_interval: float = 15.0

    # Cold-start: force immediate generation when the cache is empty.
    tip_generation_task: str = "tips.generate"
    tip_bootstrap_lock_key: str = "tips:bootstrap:lock"
    tip_bootstrap_lock_ttl: int = 30

    # --- Celery (broker/back-end for dispatching worker tasks) ---
    # Default to the same Redis instance when not explicitly provided.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # --- Chat feature ---
    chat_pending_key_prefix: str = "chat:pending:"
    chat_pending_ttl: int = 60

    # --- LLM ---
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7
    openai_api_key: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Allow a comma-separated string in the env var."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def effective_broker_url(self) -> str:
        """Celery broker URL, defaulting to the app's Redis instance."""
        return self.celery_broker_url or self.redis_url

    @property
    def effective_result_backend(self) -> str:
        """Celery result backend, defaulting to the app's Redis instance."""
        return self.celery_result_backend or self.redis_url

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single source of truth)."""
    return Settings()

