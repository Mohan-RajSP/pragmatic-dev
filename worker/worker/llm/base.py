"""Strategy pattern for LLM selection (worker copy).

Kept self-contained so the worker can be split into its own service without a
shared dependency on the backend package.
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
    def build_model(self, *, streaming: bool = False) -> BaseChatModel:
        """Return a ready-to-use LangChain chat model instance."""

