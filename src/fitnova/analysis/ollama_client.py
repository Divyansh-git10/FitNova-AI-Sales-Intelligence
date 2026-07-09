"""Thin transport wrapper around the local Ollama server.

This is deliberately "dumb": it knows how to send a prompt and get text
back, and how to ask Ollama what model/version is actually loaded. It does
NOT know about JSON schemas, retries-with-feedback, or observability
logging — that's `llm_client.py`, built on top of this. Keeping the split
means the transport layer (this file) can be unit-tested against connection
failures independently of the structured-output logic.

Transient connection failures (Ollama not running yet, a momentary
timeout) are retried with exponential backoff via `tenacity` — per docs
Section 9, "vendor API failures, retries" — before surfacing as
`OllamaConnectionError` to the caller.
"""

from __future__ import annotations

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from fitnova.core.config import Settings
from fitnova.core.logging_config import get_logger

logger = get_logger(__name__)


class OllamaConnectionError(Exception):
    """Raised when Ollama cannot be reached or errors after all transport
    retries are exhausted."""


class OllamaClient:
    """Wraps `ollama.Client` for a single configured model."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # lazily constructed so importing this module never requires `ollama` to be installed
        self._client = None
        self._model_version_cache: str | None = None

    def _get_client(self):
        if self._client is None:
            import ollama  # lazy import, mirrors WhisperTranscriber's pattern for faster-whisper

            self._client = ollama.Client(
                host=self.settings.ollama_base_url, timeout=self.settings.llm_timeout_seconds
            )
        return self._client

    def generate_json(self, prompt: str, temperature: float | None = None) -> str:
        """Send `prompt` to the configured model with JSON output mode
        forced, return the raw response text (guaranteed syntactically
        valid JSON by Ollama's `format="json"`, but NOT yet validated
        against our Pydantic schema — that's the caller's job).

        Raises `OllamaConnectionError` once transport retries are
        exhausted, so callers only ever need to catch one exception type
        for "the model server could not be reached"."""
        try:
            return self._generate_with_retry(prompt, temperature)
        except Exception as exc:  # noqa: BLE001 - final wrap after tenacity exhausts retries
            raise OllamaConnectionError(
                f"Could not reach Ollama at {self.settings.ollama_base_url} "
                f"for model '{self.settings.ollama_model}': {type(exc).__name__}: {exc}"
            ) from exc

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )
    def _generate_with_retry(self, prompt: str, temperature: float | None) -> str:
        try:
            client = self._get_client()
            response = client.generate(
                model=self.settings.ollama_model,
                prompt=prompt,
                format="json",
                options={
                    "temperature": (
                        temperature if temperature is not None else self.settings.llm_temperature
                    )
                },
            )
            return response["response"]
        except (
            Exception
        ) as exc:  # noqa: BLE001 - re-raised as our own type after tenacity exhausts retries
            logger.warning("Ollama generate() attempt failed: %s: %s", type(exc).__name__, exc)
            raise

    def get_model_version(self) -> str | None:
        """Best-effort model digest lookup, cached for the process
        lifetime. Returns None (never raises) if unavailable — model
        version is metadata for observability, not something that should
        block analysis."""
        if self._model_version_cache is not None:
            return self._model_version_cache
        try:
            client = self._get_client()
            info = client.show(self.settings.ollama_model)
            digest = getattr(info, "digest", None) or (
                info.get("digest") if isinstance(info, dict) else None
            )
            self._model_version_cache = digest or "unknown"
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not resolve Ollama model version: %s", exc)
            self._model_version_cache = "unknown"
        return self._model_version_cache
