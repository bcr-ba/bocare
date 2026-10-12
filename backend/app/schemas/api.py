from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.pipeline.orchestrator import ChatResult
from app.schemas.llm import StructuredAnswer

Language = Literal["fr", "en"]


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Omit to start a new session.")
    # The pipeline rejects anything over 2000 characters with a friendly message;
    # this hard cap only stops oversized payloads.
    message: str = Field(max_length=10_000)
    language: Language = Field(default="fr", description="Language of a new session. "
                               "Afterwards the session follows the language the user writes in.")


class Recommendation(BaseModel):
    text: str
    timeframe: str


class SourceOut(BaseModel):
    title: str
    url: str


class SafetyStatus(BaseModel):
    status: Literal["ok", "flagged", "blocked"]
    flags: List[str] = Field(default_factory=list)
    messages: List[str] = Field(default_factory=list, description="Shown to the user before the reply.")


class Verification(BaseModel):
    status: Literal["passed", "regenerated", "fallback", "llm_unavailable", "pending", "not_applicable"]
    failed_checks: List[str] = Field(default_factory=list, description="Codes of the checks that rejected a draft.")


class ChatResponse(BaseModel):
    session_id: str
    language: Language
    reply: str
    urgency_level: int = Field(ge=1, le=5)
    recommendation: Optional[Recommendation] = None
    follow_up_questions: List[str] = Field(default_factory=list)
    sources: List[SourceOut] = Field(default_factory=list)
    safety_status: SafetyStatus
    disclaimer: Optional[str] = None
    answer: Optional[StructuredAnswer] = Field(
        default=None, description="Verified structured answer; source_ids refer to `sources` (1-based).")
    verification: Verification = Field(default_factory=lambda: Verification(status="not_applicable"))

    @classmethod
    def from_result(cls, result: ChatResult) -> "ChatResponse":
        recommendation = None
        if result.recommendation:
            text, timeframe = result.recommendation
            recommendation = Recommendation(text=text, timeframe=timeframe)
        return cls(
            session_id=result.session_id,
            language=result.language,
            reply=result.reply,
            urgency_level=result.urgency_level,
            recommendation=recommendation,
            follow_up_questions=result.follow_up_questions,
            sources=[SourceOut(title=s.name, url=s.url) for s in result.sources],
            safety_status=SafetyStatus(status=result.safety_status, flags=result.safety_flags,
                                       messages=result.safety_messages),
            disclaimer=result.disclaimer,
            answer=result.answer,
            verification=Verification(status=result.verification, failed_checks=result.failed_checks),
        )


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm_configured: bool
