"""LCEL pipeline that generates a single mental-health tip.

Kept as distinct steps (prompt -> model -> output parser) per project
conventions. The compiled chain is cached so the model client is reused.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from worker.chains.tip_context import TipPromptContextBuilder
from worker.core.logging import get_logger
from worker.llm.errors import PermanentLLMError, is_permanent_llm_error
from worker.llm.factory import get_llm_strategy

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a compassionate, well-read mental-health and well-being coach. "
    "Generate ONE short, actionable, uplifting mental-health tip for a general "
    "audience. Keep it to one or two sentences. Be practical and kind. Do not "
    "include a greeting, preamble, numbering, or quotation marks — return only "
    "the tip text. "
    "Draw from a WIDE, rotating range of themes so tips feel fresh and distinct — "
    "including everyday habits (sleep, hydration, nutrition, movement, breathing, "
    "gratitude, social connection, boundaries, screen-time, journaling, rest, "
    "mindfulness) as well as deeper lenses such as neuroscience (how the brain and "
    "nervous system work), the 'old brain vs new brain' idea (the instinctive "
    "limbic/amygdala responses vs the reasoning prefrontal cortex), philosophy "
    "(e.g. Stoicism, meaning, perspective), and spirituality (presence, "
    "interconnectedness, inner stillness). Deliberately vary BOTH the theme and "
    "the wording each time rather than defaulting to the same idea; when helpful, "
    "briefly ground the tip in the concept it draws from."
)

# The `{avoid_block}` slot is filled at invoke time with the recent tips (if any)
# so the model can steer away from repeats. Kept as a template variable so the
# compiled chain stays cached and reusable.
_HUMAN_PROMPT = "Share a fresh mental-health tip for today.{avoid_block}"


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


def generate_tip_text(recent_tips: list[str] | None = None) -> str:
    """Invoke the chain and return a cleaned tip string.

    `recent_tips` (newest first) are injected into the prompt so the model avoids
    repeating or closely paraphrasing tips it already produced.
    """
    chain = build_tip_chain()
    try:
        avoid_block = (
            TipPromptContextBuilder().with_recent_tips(recent_tips or []).build()
        )
        text = chain.invoke({"avoid_block": avoid_block})
    except Exception as exc:
        # Surface the real provider error (e.g. OpenAI 429 insufficient_quota,
        # auth failures, timeouts) before it propagates to the task's retry
        # handler, which otherwise only logs a generic warning.
        logger.error(
            "LLM tip generation failed [%s]: %s",
            type(exc).__name__,
            exc,
        )
        # Permanent errors (auth/quota/bad request) can't be fixed by retrying —
        # re-raise as PermanentLLMError so the task fails fast instead of burning
        # its retry budget. Transient errors propagate as-is and are retried.
        if is_permanent_llm_error(exc):
            raise PermanentLLMError(str(exc)) from exc
        raise
    return text.strip()

