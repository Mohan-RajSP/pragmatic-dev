"""Centralized logging configuration."""

from __future__ import annotations

import logging
import sys
from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def configure_logging() -> None:
    """Configure root logging once for the whole application (idempotent)."""
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)

