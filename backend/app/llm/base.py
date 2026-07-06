"""Strategy pattern for LLM selection.

`LLMStrategy` is the abstract strategy interface. Concrete strategies (e.g.
OpenAI) implement `build_model()` returning a LangChain chat model. The
factory picks the concrete strategy from configuration, so switching providers
is a config change, not a code change (Open/Closed Principle).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from langchain_core.language_models.chat_models import BaseChatModel


class LLMStrategy(ABC):
    """Abstract strategy that yields a configured chat model."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @abstractmethod
    def build_model(self, *, streaming: bool = True) -> BaseChatModel:
        """Return a ready-to-use LangChain chat model instance."""

