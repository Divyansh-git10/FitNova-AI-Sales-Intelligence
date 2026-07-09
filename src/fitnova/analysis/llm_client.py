"""Structured, observed, retried LLM calls — the core of "reliable
tagging" (docs Section 6.3).

`LLMClient.run_structured()` is the ONLY way anything in this codebase
talks to the LLM. It guarantees:

1. **Structured output.** Ollama's `format="json"` guarantees syntactically
   valid JSON; the response is then validated against the caller's
   Pydantic `response_model` — semantic correctness, not just syntax.
2. **Retry with feedback.** A response that fails JSON parsing or schema
   validation is not a hard failure — the next attempt's prompt includes
   the specific error, giving the model a chance to self-correct, up to
   `Settings.llm_max_retries` attempts.
3. **Observability on every attempt.** Every single attempt (success or
   failure) writes one `llm_inference_logs` row — `stage`, `prompt_version`
   (from the versioned prompt file), `model_name`/`model_version`,
   `latency_ms`, `retry_count`, `success`, and (on failure) `error_message`
   plus a truncated `raw_response_excerpt` for debugging. A call that
   succeeds on attempt 3 leaves a visible trail of the two failures — see
   docs Section 12, "Failure visibility, not failure hiding."
4. **A closed failure mode.** If every attempt fails, `run_structured`
   raises `LLMResponseValidationError` — callers (the analysis
   orchestrator) treat this exactly like any other pipeline-stage failure:
   mark the call FAILED, leave it for retry on the next batch run.
"""

from __future__ import annotations

import json
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from fitnova.analysis.ollama_client import OllamaClient, OllamaConnectionError
from fitnova.analysis.prompt_manager import PromptManager
from fitnova.core.config import Settings
from fitnova.core.constants import LLMStage
from fitnova.core.logging_config import get_logger
from fitnova.db.models import LLMInferenceLog

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_RAW_RESPONSE_EXCERPT_CHARS = 2000
_MAX_ERROR_MESSAGE_CHARS = 2000


class LLMResponseValidationError(Exception):
    """Raised when every retry attempt fails to produce a schema-valid
    response. `attempts` and `last_error` are attached for the caller to
    log/report without re-deriving them."""

    def __init__(self, attempts: int, last_error: str | None) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"LLM failed to produce a valid response after {attempts} attempt(s): {last_error}"
        )


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        prompt_manager: PromptManager,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.settings = settings
        self.prompt_manager = prompt_manager
        self.ollama_client = ollama_client or OllamaClient(settings)

    def run_structured(
        self,
        *,
        stage: LLMStage,
        prompt_name: str,
        prompt_vars: dict[str, str],
        response_model: type[T],
        call_id: int,
        session: Session,
    ) -> T:
        base_prompt, prompt_version = self.prompt_manager.render(prompt_name, **prompt_vars)
        max_attempts = max(1, self.settings.llm_max_retries)
        model_version = self.ollama_client.get_model_version()

        current_prompt = base_prompt
        last_error_message: str | None = None

        for attempt in range(max_attempts):
            start = time.perf_counter()
            raw_text: str | None = None
            validated: T | None = None
            error_message: str | None = None

            try:
                raw_text = self.ollama_client.generate_json(
                    current_prompt, temperature=self.settings.llm_temperature
                )
                parsed = json.loads(raw_text)
                validated = response_model.model_validate(parsed)
            except OllamaConnectionError as exc:
                error_message = str(exc)
            except json.JSONDecodeError as exc:
                error_message = f"Response was not valid JSON: {exc}"
            except ValidationError as exc:
                error_message = f"Response did not match the required schema: {exc}"

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            success = validated is not None

            self._log_attempt(
                session=session,
                call_id=call_id,
                stage=stage,
                prompt_version=prompt_version,
                model_version=model_version,
                latency_ms=elapsed_ms,
                retry_count=attempt,
                success=success,
                error_message=error_message,
                raw_response_excerpt=raw_text,
            )

            if success:
                if attempt > 0:
                    logger.warning(
                        "LLM stage=%s recovered on attempt #%d for call_id=%s",
                        stage.value,
                        attempt + 1,
                        call_id,
                    )
                return validated

            last_error_message = error_message
            logger.warning(
                "LLM stage=%s attempt #%d failed for call_id=%s: %s",
                stage.value,
                attempt + 1,
                call_id,
                error_message,
            )
            current_prompt = (
                f"{base_prompt}\n\n"
                f"IMPORTANT: your previous response was rejected for this reason: {error_message}\n"
                f"Return ONLY corrected, valid JSON matching the required shape exactly. "
                f"No prose, no markdown fences."
            )

        raise LLMResponseValidationError(attempts=max_attempts, last_error=last_error_message)

    def _log_attempt(
        self,
        *,
        session: Session,
        call_id: int,
        stage: LLMStage,
        prompt_version: str,
        model_version: str | None,
        latency_ms: float,
        retry_count: int,
        success: bool,
        error_message: str | None,
        raw_response_excerpt: str | None,
    ) -> None:
        session.add(
            LLMInferenceLog(
                call_id=call_id,
                stage=stage,
                prompt_version=prompt_version,
                model_name=self.settings.ollama_model,
                model_version=model_version,
                temperature=self.settings.llm_temperature,
                latency_ms=latency_ms,
                retry_count=retry_count,
                success=success,
                error_message=(error_message[:_MAX_ERROR_MESSAGE_CHARS] if error_message else None),
                raw_response_excerpt=(
                    raw_response_excerpt[:_MAX_RAW_RESPONSE_EXCERPT_CHARS]
                    if raw_response_excerpt
                    else None
                ),
            )
        )
        session.flush()
