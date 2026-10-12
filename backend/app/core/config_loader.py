"""Loads and validates the YAML files in app/config and app/prompts.

Each file is read once and cached. `validate_all()` runs at startup so a broken file stops the
server immediately, with the file and field named, instead of failing during a conversation.
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Type, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from app.schemas.config import (
    AnswerPrompts,
    CarePathsConfig,
    ConversationConfig,
    FollowUpConfig,
    JudgePrompts,
    MedicalTermsConfig,
    SafetyConfig,
    TriageConfig,
    VerificationConfig,
)

APP_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = APP_DIR / "config"
PROMPTS_DIR = APP_DIR / "prompts"

T = TypeVar("T", bound=BaseModel)


class ConfigError(Exception):
    pass


def read_yaml(path: Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


def _load(path: Path, schema: Type[T]) -> T:
    try:
        return schema.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ConfigError(f"Invalid {path.relative_to(APP_DIR)}:\n{exc}") from exc


@lru_cache
def triage() -> TriageConfig:
    return _load(CONFIG_DIR / "triage.yml", TriageConfig)


@lru_cache
def care_paths() -> CarePathsConfig:
    return _load(CONFIG_DIR / "care_paths.yml", CarePathsConfig)


@lru_cache
def follow_up() -> FollowUpConfig:
    return _load(CONFIG_DIR / "follow_up_questions.yml", FollowUpConfig)


@lru_cache
def medical_terms() -> MedicalTermsConfig:
    return _load(CONFIG_DIR / "medical_terms.yml", MedicalTermsConfig)


@lru_cache
def safety() -> SafetyConfig:
    return _load(CONFIG_DIR / "safety.yml", SafetyConfig)


@lru_cache
def conversation() -> ConversationConfig:
    return _load(CONFIG_DIR / "conversation.yml", ConversationConfig)


@lru_cache
def verification() -> VerificationConfig:
    return _load(CONFIG_DIR / "verification.yml", VerificationConfig)


@lru_cache
def answer_prompts() -> AnswerPrompts:
    return _load(PROMPTS_DIR / "answer.yml", AnswerPrompts)


@lru_cache
def judge_prompts() -> JudgePrompts:
    return _load(PROMPTS_DIR / "judge.yml", JudgePrompts)


def validate_all() -> None:
    """Load every file and check references between them."""
    loaders = [triage, care_paths, follow_up, medical_terms, safety, conversation, verification,
               answer_prompts, judge_prompts]
    for load in loaders:
        load()
    unknown = {p.specialist for p in triage().symptom_profiles if p.specialist} - set(care_paths().specialists)
    if unknown:
        raise ConfigError(f"triage.yml refers to specialists missing from care_paths.yml: {sorted(unknown)}")
