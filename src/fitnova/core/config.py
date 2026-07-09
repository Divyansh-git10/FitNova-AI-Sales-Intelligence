"""Centralized, externalized configuration.

Two kinds of configuration live here, deliberately kept separate:

1. **Infra / environment settings** (`Settings`) - database URL, model
   sizes, ports, log level. These come from `.env` via `pydantic-settings`
   and change per-machine or per-deployment, never per business decision.

2. **Business-tunable configuration** (`ScoringWeightsConfig`,
   `IssueRulesConfig`) - the scoring rubric weights and the issue taxonomy
   definitions. These come from `config/weights.yaml` and
   `config/issue_rules.yaml`, are loaded through Pydantic models with
   validators, and fail loudly at bootstrap time if malformed. This is what
   "never hardcode analysis" means at the code level (see
   docs/01_PHASE1_DESIGN.md Section 13).

Nothing downstream (`scoring_engine.py`, `issue_detector.py`, etc.) is
allowed to define its own weight or threshold literal - everything is read
through `Settings.load_weights()` / `Settings.load_issue_rules()`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fitnova.core.constants import IssueType, Severity

# src/fitnova/core/config.py -> parents[3] is the project root
# (core -> fitnova -> src -> <root>)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_EXPECTED_SCORE_DIMENSIONS = {
    "needs_discovery",
    "rapport",
    "empathy",
    "listening",
    "product_knowledge",
    "objection_handling",
    "compliance",
    "trial_booking",
    "closing",
}


class Settings(BaseSettings):
    """Infra/environment configuration, loaded from `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="local")
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="console")

    database_url: str = Field(default="sqlite:///data/fitnova.db")
    sql_echo: bool = Field(default=False)

    data_dir: Path = Field(default=Path("data"))
    audio_inbox_dir: Path = Field(default=Path("data/audio/inbox"))
    processed_audio_dir: Path = Field(default=Path("data/processed"))

    weights_config_path: Path = Field(default=Path("config/weights.yaml"))
    issue_rules_config_path: Path = Field(default=Path("config/issue_rules.yaml"))
    prompts_dir: Path = Field(default=Path("src/fitnova/analysis/prompts"))

    whisper_model_size: str = Field(default="small")
    whisper_device: str = Field(default="cpu")
    whisper_compute_type: str = Field(default="int8")

    diarization_backend: str = Field(default="fallback")
    huggingface_token: str | None = Field(default=None)
    vad_aggressiveness: int = Field(default=2, ge=0, le=3)
    vad_frame_ms: int = Field(default=30)
    speaker_gap_merge_seconds: float = Field(default=0.6, ge=0)
    min_turn_duration_seconds: float = Field(default=0.3, ge=0)
    first_speaker_is_advisor: bool = Field(default=True)

    min_call_duration_seconds: float = Field(default=3.0, ge=0)
    silence_rms_threshold: float = Field(default=0.01, ge=0)

    supported_languages: str = Field(default="en,hi")
    wrong_number_max_duration_seconds: float = Field(default=20.0, ge=0)
    wrong_number_max_words: int = Field(default=25, ge=0)
    internal_call_keywords: str = Field(
        default="standup,internal call,team sync,daily sync,internal meeting"
    )

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen3:8b")
    llm_temperature: float = Field(default=0.1)
    llm_max_retries: int = Field(default=3)
    llm_timeout_seconds: int = Field(default=120)

    # Confidence calibration (docs Phase 4 addendum): numeric LLM confidence
    # is bucketed into LOW/MEDIUM/HIGH using these thresholds at the moment
    # a score/issue is produced, and the label is persisted alongside the
    # number so it never drifts if thresholds change later.
    confidence_high_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    confidence_low_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    pii_redaction_enabled: bool = Field(default=True)
    max_processing_retries: int = Field(default=3)
    idempotency_hash_algo: str = Field(default="sha256")

    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    dashboard_port: int = Field(default=8501)

    def load_weights(self) -> "ScoringWeightsConfig":
        return _load_weights_config(self.weights_config_path)

    def load_issue_rules(self) -> "IssueRulesConfig":
        return _load_issue_rules_config(self.issue_rules_config_path)

    def resolved_data_dir(self) -> Path:
        return _resolve(self.data_dir)

    def resolved_audio_inbox_dir(self) -> Path:
        return _resolve(self.audio_inbox_dir)

    def resolved_processed_audio_dir(self) -> Path:
        return _resolve(self.processed_audio_dir)

    def resolved_prompts_dir(self) -> Path:
        return _resolve(self.prompts_dir)

    def supported_languages_list(self) -> list[str]:
        return [
            lang.strip().lower() for lang in self.supported_languages.split(",") if lang.strip()
        ]

    def internal_call_keywords_list(self) -> list[str]:
        return [kw.strip().lower() for kw in self.internal_call_keywords.split(",") if kw.strip()]


class ScoringWeightsConfig(BaseModel):
    """Validated contents of `config/weights.yaml`."""

    model_config = ConfigDict(frozen=True)

    scoring_version: str
    weights: dict[str, float]

    @model_validator(mode="after")
    def _validate_weights(self) -> "ScoringWeightsConfig":
        missing = _EXPECTED_SCORE_DIMENSIONS - self.weights.keys()
        if missing:
            raise ValueError(f"weights.yaml is missing scoring dimensions: {sorted(missing)}")
        extra = self.weights.keys() - _EXPECTED_SCORE_DIMENSIONS
        if extra:
            raise ValueError(f"weights.yaml has unknown scoring dimensions: {sorted(extra)}")
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"weights.yaml weights must sum to 1.0 (+/- 0.01), got {total:.4f}")
        return self

    def weight_for(self, dimension: str) -> float:
        return self.weights[dimension]


class IssueRuleDefinition(BaseModel):
    """One issue type's externalized description, detection guidance, and
    default severity - everything a human can edit without touching code."""

    model_config = ConfigDict(frozen=True)

    default_severity: Severity
    description: str
    detection_guidance: str
    compliance_related: bool = False


class IssueRulesConfig(BaseModel):
    """Validated contents of `config/issue_rules.yaml`."""

    model_config = ConfigDict(frozen=True)

    issue_types: dict[IssueType, IssueRuleDefinition]
    fuzzy_match_threshold: int = Field(ge=0, le=100)
    min_confidence_to_surface: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_all_issue_types_present(self) -> "IssueRulesConfig":
        missing = set(IssueType) - set(self.issue_types.keys())
        if missing:
            missing_names = sorted(m.value for m in missing)
            raise ValueError(f"issue_rules.yaml is missing issue type definitions: {missing_names}")
        return self

    def rule_for(self, issue_type: IssueType) -> IssueRuleDefinition:
        return self.issue_types[issue_type]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_yaml(path: Path) -> dict:
    resolved = _resolve(path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"Config file not found: {resolved}. "
            "Did you copy .env.example to .env and check the *_CONFIG_PATH values?"
        )
    with resolved.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache
def _load_weights_config(path: Path) -> ScoringWeightsConfig:
    return ScoringWeightsConfig.model_validate(_read_yaml(path))


@lru_cache
def _load_issue_rules_config(path: Path) -> IssueRulesConfig:
    return IssueRulesConfig.model_validate(_read_yaml(path))


@lru_cache
def get_settings() -> Settings:
    return Settings()
