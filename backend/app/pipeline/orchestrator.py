"""Message flow: language detection, validation, triage, retrieval + LLM, follow-ups."""
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, List, Optional, Tuple, Union

from opentelemetry.trace import StatusCode

from app.core import config_loader
from app.core.logging_context import bind_request_id, get_request_id
from app.core.settings import get_settings
from app.core.tracing import set_attributes, span, start_root, within
from app.pipeline.follow_up import next_follow_up_questions, question_text
from app.pipeline.postprocessor import render_markdown
from app.pipeline.preprocessor import detect_language, small_talk_kind
from app.pipeline.responder import Responder, ResponderOutput
from app.pipeline.safety import InputValidator
from app.pipeline.triage import assess, care_recommendation
from app.retrieval.base import Source
from app.schemas.llm import StructuredAnswer
from app.state.session_store import InMemorySessionStore, Session, SessionStore

logger = logging.getLogger(__name__)

def texts():
    """Fixed texts (disclaimer, fallback, errors, small-talk replies) from config/conversation.yml."""
    return config_loader.conversation()


def _record_result(root, result: "ChatResult") -> None:
    """Outcome of the turn on its root span: codes and counts only, never text."""
    set_attributes(root, **{
        "bocare.language": result.language,
        "bocare.urgency_level": result.urgency_level,
        "bocare.safety_status": result.safety_status,
        "bocare.safety_flags": [f for f in result.safety_flags if f],
        "bocare.verification": result.verification,
        "bocare.failed_checks": result.failed_checks,
        "bocare.sources": len(result.sources),
    })


@dataclass
class ChatResult:
    session_id: str
    language: str
    reply: str
    urgency_level: int
    recommendation: Optional[Tuple[str, str]] = None  # (advice, timeframe); None when nothing was assessed
    follow_up_questions: List[str] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    safety_status: str = "ok"  # "ok", "flagged" or "blocked"
    safety_flags: List[str] = field(default_factory=list)
    safety_messages: List[str] = field(default_factory=list)
    disclaimer: Optional[str] = None
    answer: Optional[StructuredAnswer] = None  # the verified structured answer, when there is one
    # "passed", "regenerated", "fallback", "llm_unavailable", "pending" (preview), "not_applicable"
    verification: str = "not_applicable"
    failed_checks: List[str] = field(default_factory=list)


@dataclass
class Turn:
    """A message that passed validation and triage and still needs an answer from the model."""
    session: Session
    text: str
    recommendation: Tuple[str, str]
    follow_up_questions: List[str]
    safety_flags: List[str]
    safety_messages: List[str]


class Orchestrator:
    def __init__(self, responder: Responder, validator: Optional[InputValidator] = None,
                 default_language: Optional[str] = None, store: Optional[SessionStore] = None):
        self.responder = responder
        self.validator = validator or InputValidator()
        self.default_language = default_language or get_settings().default_language
        self.store = store or InMemorySessionStore()

    @property
    def llm_configured(self) -> bool:
        return self.responder.llm_configured

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.store.get(session_id) if session_id else None

    def _get_or_create_session(self, session_id: Optional[str], language: Optional[str]) -> Session:
        session = self.get_session(session_id)
        if session is None:
            session = self.store.create(language or self.default_language)
            logger.info("Session %s started (%s)", session.session_id, session.language)
        return session

    def handle(self, message: str, session_id: Optional[str] = None, language: Optional[str] = None,
               request_id: Optional[str] = None) -> ChatResult:
        """Process one user message. `language` only sets the language of a new session;
        after that it follows the language the user writes in."""
        request_id = request_id or get_request_id()
        root = start_root("chat.turn", **{"bocare.request_id": request_id, "bocare.endpoint": "chat"})
        try:
            with self._step(root, request_id):
                session = self._get_or_create_session(session_id, language)
                root.set_attribute("bocare.session_id", session.session_id)
                try:
                    step = self.prepare(message, session)
                    result = step if isinstance(step, ChatResult) else self.complete(step)
                except Exception as exc:
                    root.record_exception(exc)
                    root.set_status(StatusCode.ERROR)
                    logger.exception("Session %s: unexpected error", session.session_id)
                    result = self._internal_error(session)
                self.store.save(session)
            _record_result(root, result)
            return result
        finally:
            root.end()

    @staticmethod
    @contextmanager
    def _step(root, request_id: str):
        """One synchronous step of a turn: its spans attach to the turn's root span and its logs carry
        the request ID, even when streaming runs each step on a different thread."""
        with within(root), bind_request_id(request_id):
            yield

    def _internal_error(self, session: Session) -> ChatResult:
        return ChatResult(session.session_id, session.language, texts().internal_error[session.language],
                          session.urgency_level)

    def prepare(self, message: str, session: Session) -> Union[ChatResult, Turn]:
        """The fast, deterministic part: validation, triage, recommendation and follow-ups.
        Returns a final ChatResult when no generation is needed (blocked input, small talk)."""
        session.language = detect_language(message, session.language)
        language = session.language

        with span("safety.validate") as check:
            validation = self.validator.validate(message, session.session_id, language)
            set_attributes(check, **{"safety.valid": validation.is_valid, "safety.reason": validation.reason,
                                     "safety.flags": validation.flags})
        if not validation.is_valid:
            return ChatResult(session.session_id, language, validation.error, session.urgency_level,
                              safety_status="blocked", safety_flags=[validation.reason],
                              safety_messages=[validation.error])

        small_talk = small_talk_kind(validation.text)
        if small_talk:
            return ChatResult(session.session_id, language, texts().small_talk[small_talk].reply[language],
                              session.urgency_level)

        with span("triage.assess") as triage_span:
            triage = assess(validation.text, validation.self_harm)
            set_attributes(triage_span, **{"triage.urgency": triage.urgency, "triage.symptoms": triage.symptoms})
        session.symptoms.extend(s for s in triage.symptoms if s not in session.symptoms)
        session.urgency_level = max(session.urgency_level, triage.urgency)
        if triage.urgency >= config_loader.triage().log_from_level:
            # Log the triage outcome only; the message itself is health data.
            logger.warning("Session %s: urgency %d, symptoms=%s", session.session_id, triage.urgency, triage.symptoms)

        follow_ups: List[str] = []
        if len(session.history) + 2 <= config_loader.follow_up().ask_until_message:
            questions = next_follow_up_questions(session.asked_questions, language)
            session.asked_questions.extend(questions)
            follow_ups = [question_text(q, language) for q in questions]

        return Turn(
            session=session,
            text=validation.text,
            recommendation=care_recommendation(session.urgency_level, triage.specialist, language),
            follow_up_questions=follow_ups,
            safety_flags=list(validation.flags),
            safety_messages=list(validation.warnings),
        )

    def preview(self, turn: Turn) -> ChatResult:
        """What can be shown before the model answers: triage, recommendation, safety, follow-ups."""
        session = turn.session
        return ChatResult(
            session_id=session.session_id,
            language=session.language,
            reply="",
            urgency_level=session.urgency_level,
            recommendation=turn.recommendation,
            follow_up_questions=turn.follow_up_questions,
            safety_status="flagged" if turn.safety_flags else "ok",
            safety_flags=turn.safety_flags,
            safety_messages=turn.safety_messages,
            disclaimer=texts().disclaimer[session.language],
            verification="pending",
        )

    def complete(self, turn: Turn) -> ChatResult:
        """The slow part: retrieval, generation and verification."""
        session = turn.session
        output = self.responder.respond(turn.text, session.history, session.language, session.urgency_level,
                                        turn.recommendation[0])
        return self.finish(turn, output)

    def stream(self, message: str, session_id: Optional[str] = None, language: Optional[str] = None,
               request_id: Optional[str] = None) -> Iterator[Tuple[str, Any]]:
        """Same pipeline as handle(), as events: ("triage", ChatResult) as soon as triage is done,
        ("sources", [Source]), ("status", stage name), and finally ("done", ChatResult).
        The answer is only sent once it has passed verification."""
        request_id = request_id or get_request_id()
        root = start_root("chat.turn", **{"bocare.request_id": request_id, "bocare.endpoint": "chat/stream"})
        # Every `with self._step(...)` block below is free of `yield`: a span or context must not stay
        # open across events, because the next event may be produced on another thread.
        try:
            with self._step(root, request_id):
                session = self._get_or_create_session(session_id, language)
                root.set_attribute("bocare.session_id", session.session_id)
            try:
                with self._step(root, request_id):
                    step = self.prepare(message, session)
                    if isinstance(step, ChatResult):
                        self.store.save(session)
                if isinstance(step, ChatResult):
                    _record_result(root, step)
                    yield "done", step
                    return
                yield "triage", self.preview(step)
                yield "status", "retrieving"
                with self._step(root, request_id):
                    sources = self.responder.retrieve(step.text)
                yield "sources", sources
                steps = self.responder.respond_steps(step.text, session.history, session.language,
                                                     session.urgency_level, step.recommendation[0], sources)
                output = None
                while output is None:
                    with self._step(root, request_id):
                        event = next(steps)
                    if isinstance(event, str):
                        yield "status", event
                    else:
                        output = event
                with self._step(root, request_id):
                    result = self.finish(step, output)
                    self.store.save(session)
                _record_result(root, result)
                yield "done", result
            except Exception as exc:
                root.record_exception(exc)
                root.set_status(StatusCode.ERROR)
                with self._step(root, request_id):
                    logger.exception("Session %s: unexpected error", session.session_id)
                yield "done", self._internal_error(session)
        finally:
            root.end()

    def finish(self, turn: Turn, output: ResponderOutput) -> ChatResult:
        session, language = turn.session, turn.session.language
        advice = turn.recommendation[0]
        if output.answer is not None:
            reply = render_markdown(output.answer, language)
        elif output.status == "fallback":
            reply = texts().fallback_reply[language].format(advice=advice)
        else:
            reply = texts().model_unavailable[language]

        session.history.append({"role": "user", "content": turn.text})
        session.history.append({"role": "assistant", "content": reply})

        result = self.preview(turn)
        result.reply = reply
        result.answer = output.answer
        result.sources = output.sources
        result.verification = output.status
        result.failed_checks = output.failed_checks
        return result
