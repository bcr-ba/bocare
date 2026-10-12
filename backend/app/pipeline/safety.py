"""Checks run on user input before it reaches triage and the model (config/safety.yml)."""
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core import config_loader
from app.core.settings import get_settings
from app.pipeline.preprocessor import normalize_whitespace

_CONFIG = config_loader.safety()
MAX_INPUT_LENGTH = _CONFIG.max_input_length

# Catches the obvious "ignore your instructions" attempts. This is a speed bump,
# not a defence: the system prompt and output verification still have to hold.
INJECTION_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _CONFIG.injection_patterns]


@dataclass
class ValidationResult:
    is_valid: bool
    text: str = ""
    error: Optional[str] = None
    reason: Optional[str] = None  # why the input was blocked
    warnings: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)  # e.g. "self_harm", "medication_request"

    @property
    def self_harm(self) -> bool:
        return "self_harm" in self.flags


class RateLimiter:
    """Sliding one-minute window per key, in process memory."""

    def __init__(self, max_per_minute: Optional[int] = None):
        self.max_per_minute = max_per_minute or get_settings().rate_limit_per_minute
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits[key] if now - t < 60]
            allowed = len(hits) < self.max_per_minute
            if allowed:
                hits.append(now)
            self._hits[key] = hits
            return allowed


def message(key: str, language: str) -> str:
    return _CONFIG.messages[key][language].format(max_length=MAX_INPUT_LENGTH)


class InputValidator:
    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.rate_limiter = rate_limiter or RateLimiter()

    def validate(self, text: str, session_id: str, language: str) -> ValidationResult:
        text = normalize_whitespace(text)

        if len(text) < _CONFIG.min_input_length:
            return self._blocked("too_short", language)
        if len(text) > MAX_INPUT_LENGTH:
            return self._blocked("too_long", language)
        if not self.rate_limiter.allow(session_id):
            return self._blocked("rate_limited", language)
        if any(pattern.search(text) for pattern in INJECTION_PATTERNS):
            return self._blocked("prompt_injection", language)

        lowered = text.lower()
        result = ValidationResult(True, text=text)
        if any(keyword in lowered for keyword in _CONFIG.self_harm_keywords):
            result.flags.append("self_harm")
            result.warnings.append(message("self_harm", language))
        if any(keyword in lowered for keyword in _CONFIG.medication_keywords):
            result.flags.append("medication_request")
            result.warnings.append(message("medication_request", language))
        return result

    @staticmethod
    def _blocked(reason: str, language: str) -> ValidationResult:
        return ValidationResult(False, error=message(reason, language), reason=reason)
