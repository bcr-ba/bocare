"""Message flow: language detection, validation, triage, retrieval + LLM, follow-ups."""
import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from app.core import config_loader
from app.core.settings import get_settings
from app.pipeline.follow_up import QuestionId, next_follow_up_questions, question_text
from app.pipeline.postprocessor import render_markdown
from app.pipeline.preprocessor import detect_language, small_talk_kind
from app.pipeline.responder import Responder, ResponderOutput
from app.pipeline.safety import InputValidator
from app.pipeline.triage import assess, care_recommendation
from app.retrieval.base import Source
from app.schemas.llm import StructuredAnswer

logger = logging.getLogger(__name__)

def texts():
    """Fixed texts (disclaimer, fallback, errors, small-talk replies) from config/conversation.yml."""
    return config_loader.conversation()


@dataclass
class Session:
    session_id: str
    language: str = "fr"
    urgency_level: int = 1
    symptoms: List[str] = field(default_factory=list)
    history: List[Dict[str, str]] = field(default_factory=list)
    asked_questions: List[QuestionId] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return asdict(self)


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
                 default_language: Optional[str] = None):
        self.responder = responder
        self.validator = validator or InputValidator()
        self.default_language = default_language or get_settings().default_language
        self.sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    @property
    def llm_configured(self) -> bool:
        return self.responder.llm_configured

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def _get_or_create_session(self, session_id: Optional[str], language: Optional[str]) -> Session:
        with self._lock:
            if session_id in self.sessions:
                return self.sessions[session_id]
            session = Session(session_id=str(uuid.uuid4()), language=language or self.default_language)
            self.sessions[session.session_id] = session
        logger.info("Session %s started (%s)", session.session_id, session.language)
        return session

    def handle(self, message: str, session_id: Optional[str] = None, language: Optional[str] = None) -> ChatResult:
        """Process one user message. `language` only sets the language of a new session;
        after that it follows the language the user writes in."""
        session = self._get_or_create_session(session_id, language)
        try:
            step = self.prepare(message, session)
            return step if isinstance(step, ChatResult) else self.complete(step)
        except Exception:
            logger.exception("Session %s: unexpected error", session.session_id)
            return self._internal_error(session)

    def _internal_error(self, session: Session) -> ChatResult:
        return ChatResult(session.session_id, session.language, texts().internal_error[session.language],
                          session.urgency_level)

    def prepare(self, message: str, session: Session) -> Union[ChatResult, Turn]:
        """The fast, deterministic part: validation, triage, recommendation and follow-ups.
        Returns a final ChatResult when no generation is needed (blocked input, small talk)."""
        session.language = detect_language(message, session.language)
        language = session.language

        validation = self.validator.validate(message, session.session_id, language)
        if not validation.is_valid:
            return ChatResult(session.session_id, language, validation.error, session.urgency_level,
                              safety_status="blocked", safety_flags=[validation.reason],
                              safety_messages=[validation.error])

        small_talk = small_talk_kind(validation.text)
        if small_talk:
            return ChatResult(session.session_id, language, texts().small_talk[small_talk].reply[language],
                              session.urgency_level)

        triage = assess(validation.text, validation.self_harm)
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

    def stream(self, message: str, session_id: Optional[str] = None,
               language: Optional[str] = None) -> Iterator[Tuple[str, Any]]:
        """Same pipeline as handle(), as events: ("triage", ChatResult) as soon as triage is done,
        ("sources", [Source]), ("status", stage name), and finally ("done", ChatResult).
        The answer is only sent once it has passed verification."""
        session = self._get_or_create_session(session_id, language)
        try:
            step = self.prepare(message, session)
            if isinstance(step, ChatResult):
                yield "done", step
                return
            yield "triage", self.preview(step)
            yield "status", "retrieving"
            sources = self.responder.retrieve(step.text)
            yield "sources", sources
            output = None
            for event in self.responder.respond_steps(step.text, session.history, session.language,
                                                      session.urgency_level, step.recommendation[0], sources):
                if isinstance(event, str):
                    yield "status", event
                else:
                    output = event
            yield "done", self.finish(step, output)
        except Exception:
            logger.exception("Session %s: unexpected error", session.session_id)
            yield "done", self._internal_error(session)

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
