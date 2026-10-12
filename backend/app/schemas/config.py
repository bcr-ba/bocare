"""Schemas for the YAML files in app/config and app/prompts. Loading fails fast, with the file
and field named, when a value is missing, mistyped, untranslated or not a valid regex."""
import re
from typing import Annotated, Dict, List, Optional

from pydantic import AfterValidator, BaseModel, Field, model_validator

LANGUAGES = ("fr", "en")


def _both_languages(value: Dict[str, str]) -> Dict[str, str]:
    missing = [lang for lang in LANGUAGES if lang not in value]
    if missing:
        raise ValueError(f"missing translation for {missing}")
    return value


def _valid_regexes(patterns: List[str]) -> List[str]:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
    return patterns


Localized = Annotated[Dict[str, str], AfterValidator(_both_languages)]
Regexes = Annotated[List[str], AfterValidator(_valid_regexes)]
Level = Annotated[int, Field(ge=1, le=5)]


class SymptomProfile(BaseModel):
    name: str
    indicators: List[str]
    urgency: Level
    specialist: Optional[str] = None


class TriageConfig(BaseModel):
    emergency_level: Level
    log_from_level: Level
    red_flags: List[str]
    symptom_profiles: List[SymptomProfile]
    urgency_keywords: Dict[str, Level]


class CareStep(BaseModel):
    advice: str
    timeframe: str


class CarePathsConfig(BaseModel):
    specialist_suggested_at_level: Level
    specialist_label: Localized
    specialists: Dict[str, Localized]
    levels: Dict[Level, Dict[str, CareStep]]

    @model_validator(mode="after")
    def every_level_in_every_language(self) -> "CarePathsConfig":
        if set(self.levels) != {1, 2, 3, 4, 5}:
            raise ValueError(f"levels must be exactly 1-5, got {sorted(self.levels)}")
        for level, steps in self.levels.items():
            _both_languages(steps)
        return self


class FollowUpConfig(BaseModel):
    ask_until_message: int
    max_per_turn: int
    categories: Dict[str, Dict[str, List[str]]]

    @model_validator(mode="after")
    def same_questions_in_every_language(self) -> "FollowUpConfig":
        for name, by_language in self.categories.items():
            _both_languages(by_language)
            if len({len(questions) for questions in by_language.values()}) != 1:
                raise ValueError(f"category {name!r} has a different number of questions per language")
        return self


class SearchTerm(BaseModel):
    term: str
    phrases: List[str]


class MedicalTermsConfig(BaseModel):
    max_terms: int
    terms: List[SearchTerm]


class SafetyConfig(BaseModel):
    min_input_length: int
    max_input_length: int
    injection_patterns: Regexes
    self_harm_keywords: List[str]
    medication_keywords: List[str]
    messages: Dict[str, Localized]

    @model_validator(mode="after")
    def all_messages_present(self) -> "SafetyConfig":
        required = {"too_short", "too_long", "rate_limited", "prompt_injection", "self_harm", "medication_request"}
        missing = required - set(self.messages)
        if missing:
            raise ValueError(f"missing messages: {sorted(missing)}")
        return self


class SmallTalk(BaseModel):
    pattern: str
    reply: Localized

    @model_validator(mode="after")
    def pattern_compiles(self) -> "SmallTalk":
        _valid_regexes([self.pattern])
        return self


class OutputCleanup(BaseModel):
    self_reference_phrases: Regexes
    preamble_pattern: str


class ConversationConfig(BaseModel):
    small_talk: Dict[str, SmallTalk]
    disclaimer: Localized
    model_unavailable: Localized
    fallback_reply: Localized
    internal_error: Localized
    answer_sections: Dict[str, Dict[str, str]]
    output_cleanup: OutputCleanup


class VerificationConfig(BaseModel):
    delay_advice_min_level: Level
    delay_advice: Regexes
    negations: Regexes
    negation_window_words: int
    dose_units: Regexes
    diagnostic_certainty: Regexes


class AnswerPrompts(BaseModel):
    history_turns: int
    source_format: str
    system: Localized
    urgent_rule: Localized
    no_sources: Localized
    retry_note: Localized


class JudgePrompts(BaseModel):
    system: str
    user: str
    no_sources: str
