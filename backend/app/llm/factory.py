"""Factory that selects an `LLMStrategy` based on configuration."""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings, get_settings
from app.llm.base import LLMStrategy
from app.llm.openai_strategy import OpenAIStrategy

# Registry maps a provider key -> factory callable.
# Add new providers here without touching call sites (Open/Closed Principle).
_STRATEGY_REGISTRY: dict[str, Callable[[Settings], LLMStrategy]] = {
    "openai": OpenAIStrategy,
}


def get_llm_strategy(settings: Settings | None = None) -> LLMStrategy:
    """Return the configured LLM strategy instance."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()
    try:
        factory = _STRATEGY_REGISTRY[provider]
    except KeyError as exc:
        supported = ", ".join(sorted(_STRATEGY_REGISTRY))
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Supported providers: {supported}."
        ) from exc
    return factory(settings)

