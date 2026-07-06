"""LCEL pipeline that generates a single mental-health tip.

Kept as distinct steps (prompt -> model -> output parser) per project
conventions. The compiled chain is cached so the model client is reused.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from worker.llm.factory import get_llm_strategy

_SYSTEM_PROMPT = (
    "You are a compassionate mental-health and well-being coach. Generate ONE "
    "short, actionable, uplifting mental-health tip for a general audience. "
    "Keep it to one or two sentences. Be practical and kind. Do not include a "
    "greeting, preamble, numbering, or quotation marks — return only the tip text."
)

_HUMAN_PROMPT = "Share a fresh mental-health tip for today."


@lru_cache
def build_tip_chain() -> Runnable:
    """Compile and cache the tip-generation LCEL chain."""
    # Step 1 — prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", _HUMAN_PROMPT),
        ]
    )
    # Step 2 — model (no streaming needed for a one-shot generation)
    model = get_llm_strategy().build_model(streaming=False)
    # Step 3 — output parser (extract plain text)
    parser = StrOutputParser()
    # Compose
    return prompt | model | parser


def generate_tip_text() -> str:
    """Invoke the chain and return a cleaned tip string."""
    chain = build_tip_chain()
    text = chain.invoke({})
    return text.strip()

