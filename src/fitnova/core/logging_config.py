"""Structured logging setup.

Two output formats, chosen via `Settings.log_format` (never hardcoded):

- ``console`` — Rich-formatted, human-readable, for local development.
- ``json`` — one JSON object per line, for log shipping / production.

Call sites should never call `logging.basicConfig()` themselves; everything
goes through `configure_logging()` once, at bootstrap, and `get_logger()`
thereafter. This keeps log formatting centralized and swappable.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from rich.logging import RichHandler

from fitnova.core.config import Settings
from fitnova.core.constants import LogFormat

_CONFIGURED = False

# Extra attributes we allow structured log calls to attach via `extra={...}`
# and that the JSON formatter will surface if present on the record.
_STRUCTURED_EXTRA_KEYS = ("component", "call_id", "stage", "content_hash")


class _JsonFormatter(logging.Formatter):
    """Minimal, dependency-free JSON line formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _STRUCTURED_EXTRA_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Configure the root logger exactly once per process.

    Safe to call multiple times (e.g. once from the API, once from a test
    fixture) — subsequent calls are no-ops so handlers are never duplicated.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    if settings.log_format == LogFormat.JSON.value:
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
    else:
        handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            markup=False,
            log_time_format="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(logging.Formatter("%(name)s — %(message)s"))

    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Standard logger accessor. Use `__name__` as `name` at call sites so
    log lines are traceable to the module that emitted them."""
    return logging.getLogger(name)


def reset_logging_for_tests() -> None:
    """Allow test fixtures to reconfigure logging between test runs."""
    global _CONFIGURED
    _CONFIGURED = False
    logging.getLogger().handlers.clear()
