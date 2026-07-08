"""Builder for the supplementary context injected into the tip-generation prompt.

The tip prompt has an `{avoid_block}` slot for extra guidance assembled at
runtime. Rather than string-concatenating that inline, we use the **builder
pattern** so context sources can be layered in fluently and independently:

    context = (
        TipPromptContextBuilder()
        .with_recent_tips(recent_tips)   # anti-duplication
        # .with_themes(...)              # future: steer toward specific domains
        # .with_time_of_day(...)         # future: contextual tips
        .build()
    )

Each `with_*` method is a no-op when given empty input and returns `self`, so
callers can chain unconditionally. `build()` returns a ready-to-inject string
(empty when nothing was added), prefixed with spacing so it slots cleanly after
the base human prompt.
"""

from __future__ import annotations

from collections.abc import Sequence


class TipPromptContextBuilder:
    """Fluently assembles the tip prompt's supplementary context block."""

    def __init__(self) -> None:
        self._sections: list[str] = []

    def with_recent_tips(self, recent_tips: Sequence[str]) -> TipPromptContextBuilder:
        """Add an 'avoid these recent tips' section (no-op if empty).

        Primes the model against repeating or closely paraphrasing tips it has
        already produced.
        """
        if recent_tips:
            joined = "\n".join(f"- {tip}" for tip in recent_tips)
            self._sections.append(
                "Do NOT repeat or closely paraphrase any of these recent tips — "
                "choose a clearly different theme and different wording:\n" + joined
            )
        return self

    def build(self) -> str:
        """Return the assembled context block (empty string if nothing added)."""
        if not self._sections:
            return ""
        # Leading blank line separates the context from the base human prompt.
        return "\n\n" + "\n\n".join(self._sections)

