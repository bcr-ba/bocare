import re
from typing import Optional

from langdetect import DetectorFactory, LangDetectException, detect

from app.core import config_loader

DetectorFactory.seed = 0  # make langdetect deterministic

SUPPORTED_LANGUAGES = ("fr", "en")


def detect_language(text: str, fallback: str) -> str:
    try:
        language = detect(text)
    except LangDetectException:
        return fallback
    return language if language in SUPPORTED_LANGUAGES else fallback


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


# Whole-message greetings, thanks and bare requests for help (config/conversation.yml):
# answered with a fixed reply, no triage or model call.
_SMALL_TALK = {kind: re.compile(entry.pattern, re.IGNORECASE)
               for kind, entry in config_loader.conversation().small_talk.items()}


def small_talk_kind(text: str) -> Optional[str]:
    """Return "greeting", "help" or "thanks" when the whole message is just that, else None."""
    text = normalize_whitespace(text)
    for kind, pattern in _SMALL_TALK.items():
        if pattern.match(text):
            return kind
    return None
