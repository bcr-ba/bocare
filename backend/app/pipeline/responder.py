"""Generates a structured answer and verifies it: one regeneration, then the caller falls back."""
import logging
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence, Union

from app.core.settings import get_settings
from app.llm.client import LLMClient, LLMError
from app.llm.prompts import build_messages
from app.pipeline.postprocessor import clean_answer, parse_answer
from app.pipeline.verifier import Verifier
from app.retrieval.base import Retriever, Source
from app.schemas.llm import ANSWER_SCHEMA, StructuredAnswer

logger = logging.getLogger(__name__)


@dataclass
class ResponderOutput:
    answer: Optional[StructuredAnswer]  # None unless an answer passed verification
    sources: List[Source]
    status: str  # "passed", "regenerated", "fallback" or "llm_unavailable"
    failed_checks: List[str] = field(default_factory=list)


class Responder:
    def __init__(self, retriever: Retriever, llm: LLMClient, verifier: Optional[Verifier] = None,
                 max_attempts: Optional[int] = None):
        self.retriever = retriever
        self.llm = llm
        self.verifier = verifier or Verifier()
        self.max_attempts = max_attempts or get_settings().llm_max_attempts

    @property
    def llm_configured(self) -> bool:
        return getattr(self.llm, "configured", True)

    def retrieve(self, text: str) -> List[Source]:
        return self.retriever.search(text)

    def respond(self, text: str, history: Sequence[Dict[str, str]], language: str, urgency_level: int,
                advice: str, sources: Optional[List[Source]] = None) -> ResponderOutput:
        if sources is None:
            sources = self.retrieve(text)
        for event in self.respond_steps(text, history, language, urgency_level, advice, sources):
            if isinstance(event, ResponderOutput):
                return event
        raise RuntimeError("respond_steps ended without a result")

    def respond_steps(self, text: str, history: Sequence[Dict[str, str]], language: str, urgency_level: int,
                      advice: str, sources: List[Source]) -> Iterator[Union[str, ResponderOutput]]:
        """Yields stage names ("generating", "verifying", "regenerating") and finally a ResponderOutput."""
        failed: List[str] = []
        rejected_for: Optional[List[str]] = None
        for attempt in range(self.max_attempts):
            yield "generating" if attempt == 0 else "regenerating"
            messages = build_messages(text, history, sources, language, urgency_level, advice, rejected_for)
            try:
                raw = self.llm.complete(messages, schema=ANSWER_SCHEMA)
            except LLMError as exc:
                logger.error("LLM call failed: %s", exc)
                yield ResponderOutput(None, sources, "llm_unavailable", failed)
                return

            answer, structured = parse_answer(raw)
            if not structured:
                logger.info("Model ignored the JSON schema; using its text as the summary")
            answer = clean_answer(answer, len(sources))
            yield "verifying"
            failures = self.verifier.check(answer, urgency_level, advice, sources)
            if not failures:
                yield ResponderOutput(answer, sources, "passed" if attempt == 0 else "regenerated", failed)
                return
            # Log the failed checks only, never the generated text.
            logger.warning("Answer rejected (attempt %d/%d): %s", attempt + 1, self.max_attempts, failures)
            failed += failures
            rejected_for = failures
        yield ResponderOutput(None, sources, "fallback", failed)
