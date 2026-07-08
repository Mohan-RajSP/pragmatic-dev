"""LLM error classification (transient vs. permanent).

Retrying only helps for *transient* failures (timeouts, connection blips,
genuine rate limiting). Some provider errors are *permanent* for the current
configuration — retrying just burns the retry budget and delays the inevitable:

- Authentication / permission errors (bad or unauthorized API key).
- Bad request / not found (e.g. an invalid model name).
- Quota exhaustion (`insufficient_quota`) — a billing problem, not a rate limit.

Classification is done by exception class *name* and error *code* rather than by
importing the provider SDK, so this module stays decoupled from any one provider
and resilient across SDK versions.
"""

from __future__ import annotations

# OpenAI (and langchain-openai) raise these for non-retryable conditions.
_PERMANENT_ERROR_TYPE_NAMES = frozenset(
    {
        "AuthenticationError",   # 401 — invalid/missing key
        "PermissionDeniedError",  # 403 — key lacks access
        "BadRequestError",       # 400 — malformed request
        "NotFoundError",         # 404 — e.g. unknown model
    }
)

# RateLimitError is normally transient, EXCEPT when it signals quota exhaustion.
_PERMANENT_ERROR_CODES = frozenset({"insufficient_quota"})


class PermanentLLMError(Exception):
    """An LLM failure that cannot be resolved by retrying (auth/quota/bad request)."""


def _error_code(exc: Exception) -> str | None:
    """Best-effort extraction of a provider error code (e.g. 'insufficient_quota')."""
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("code")
        if isinstance(inner, str):
            return inner
    return None


def is_permanent_llm_error(exc: Exception) -> bool:
    """Return True if retrying `exc` cannot succeed with the current config."""
    if type(exc).__name__ in _PERMANENT_ERROR_TYPE_NAMES:
        return True

    code = _error_code(exc)
    if code is not None and code in _PERMANENT_ERROR_CODES:
        return True

    # Fallback for wrapped errors where the code isn't structurally accessible.
    return any(marker in str(exc) for marker in _PERMANENT_ERROR_CODES)

