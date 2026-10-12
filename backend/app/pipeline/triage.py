"""Rule-based triage. The urgency level comes from these rules (config/triage.yml), never from the model."""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.core import config_loader


@dataclass
class TriageResult:
    symptoms: List[str]
    urgency: int
    specialist: Optional[str]


def analyze_symptoms(text: str) -> Tuple[List[str], int, Optional[str]]:
    """Return (matched symptom names, urgency 1-5, specialist key or None)."""
    rules = config_loader.triage()
    text = text.lower()
    symptoms: List[str] = []
    urgency = 1
    specialist = None

    for profile in rules.symptom_profiles:
        if any(indicator in text for indicator in profile.indicators):
            symptoms.append(profile.name)
            urgency = max(urgency, profile.urgency)
            specialist = profile.specialist or specialist

    if any(keyword in text for keyword in rules.red_flags):
        urgency = rules.emergency_level
    for keyword, level in rules.urgency_keywords.items():
        if keyword in text:
            urgency = max(urgency, level)

    return symptoms, urgency, specialist


def assess(text: str, self_harm: bool = False) -> TriageResult:
    symptoms, urgency, specialist = analyze_symptoms(text)
    if self_harm:
        urgency = config_loader.triage().emergency_level
    return TriageResult(symptoms, urgency, specialist)


def care_recommendation(urgency: int, specialist: Optional[str], language: str) -> Tuple[str, str]:
    """Return (advice, timeframe) for an urgency level (config/care_paths.yml)."""
    paths = config_loader.care_paths()
    step = paths.levels[urgency][language]
    advice = step.advice
    if specialist and urgency == paths.specialist_suggested_at_level:
        advice += f" ({paths.specialist_label[language]} : {paths.specialists[specialist][language]})"
    return advice, step.timeframe
