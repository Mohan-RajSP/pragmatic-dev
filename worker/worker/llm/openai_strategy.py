"""OpenAI concrete LLM strategy (worker copy)."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from worker.core.config import Settings
from worker.llm.base import LLMStrategy


class OpenAIStrategy(LLMStrategy):
    """Builds a `ChatOpenAI` model from settings."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "openai"

    def build_model(self, *, streaming: bool = False) -> BaseChatModel:
        if not self._settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Provide it via the environment / .env file."
            )
        return ChatOpenAI(
            model=self._settings.llm_model,
            temperature=self._settings.llm_temperature,
            streaming=streaming,
            api_key=self._settings.openai_api_key,
        )

