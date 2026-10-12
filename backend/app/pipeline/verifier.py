"""Checks a generated answer must pass before a patient sees it.

Deterministic rules run first and cost nothing. The judge (an LLM call) runs only when the
rules pass and the urgency is at least `judge_min_level`. Failures are returned as short
codes, which are safe to log and to return through the API: they never contain the text.
"""
import logging
import re
from typing import List, Optional

from app.core import config_loader
from app.core.settings import get_settings
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_judge_messages
from app.retrieval.base import Source
from app.schemas.llm import JUDGE_SCHEMA, JudgeVerdict, StructuredAnswer

logger = logging.getLogger(__name__)

# The phrase lists live in config/verification.yml; here they become regexes.
_RULES = config_loader.verification()

# Advice to wait or stay home: unacceptable when triage says to get care within hours or now.
DELAY_ADVICE = re.compile(r"\b(" + "|".join(_RULES.delay_advice) + r")\b", re.IGNORECASE)
# "Do not wait", "don't wait", "n'attendez pas", "il ne faut pas attendre" are the advice we want.
NEGATED = re.compile("(" + "|".join(_RULES.negations) + r")\W*(\w+\W+){0,%d}$" % _RULES.negation_window_words,
                     re.IGNORECASE)
DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(" + "|".join(_RULES.dose_units) + r")\b", re.IGNORECASE)
# Restating a symptom ("you have a sore throat") is fine; asserting a diagnosis is not.
DIAGNOSTIC_CERTAINTY = re.compile(r"\b(" + "|".join(_RULES.diagnostic_certainty) + ")", re.IGNORECASE)


def _has_unnegated_delay(text: str) -> bool:
    return any(not NEGATED.search(text[:m.start()]) for m in DELAY_ADVICE.finditer(text))


def rule_failures(answer: StructuredAnswer, urgency_level: int) -> List[str]:
    texts = [t.replace("’", "'") for t in answer.texts()]
    failures = []
    if urgency_level >= _RULES.delay_advice_min_level and any(_has_unnegated_delay(t) for t in texts):
        failures.append("delay_advice_at_high_urgency")
    if any(DOSE.search(t) for t in texts):
        failures.append("dose")
    if any(DIAGNOSTIC_CERTAINTY.search(t) for t in texts):
        failures.append("diagnostic_certainty")
    return failures


class Verifier:
    def __init__(self, judge: Optional[LLMClient] = None, judge_min_level: Optional[int] = None):
        settings = get_settings()
        self.judge = judge
        self.judge_min_level = judge_min_level or settings.judge_min_level
        self.judge_max_tokens = settings.judge_max_tokens

    def check(self, answer: StructuredAnswer, urgency_level: int, advice: str,
              sources: List[Source]) -> List[str]:
        failures = rule_failures(answer, urgency_level)
        if failures or self.judge is None or urgency_level < self.judge_min_level:
            return failures
        return self._judge(answer, urgency_level, advice, sources)

    def _judge(self, answer: StructuredAnswer, urgency_level: int, advice: str,
               sources: List[Source]) -> List[str]:
        messages = build_judge_messages(answer, sources, urgency_level, advice)
        try:
            raw = self.judge.complete(messages, schema=JUDGE_SCHEMA, max_tokens=self.judge_max_tokens)
            verdict = JudgeVerdict.model_validate_json(raw[raw.find("{"):raw.rfind("}") + 1])
        except (LLMError, ValueError) as exc:
            # The rules have passed; an unavailable judge doesn't block the answer.
            logger.warning("Judge unavailable, answer kept on rule checks only: %s", exc)
            return []
        failures = []
        if not verdict.supported:
            failures.append("judge_unsupported_claim")
        if verdict.contradicts_recommendation:
            failures.append("judge_contradicts_recommendation")
        return failures
