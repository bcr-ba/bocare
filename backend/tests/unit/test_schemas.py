import pytest
from pydantic import ValidationError

from app.pipeline.orchestrator import ChatResult
from app.retrieval.base import Source
from app.schemas.api import ChatRequest, ChatResponse


def test_chat_request_defaults():
    request = ChatRequest(message="hello")
    assert request.session_id is None
    assert request.language == "fr"


def test_chat_request_rejects_unknown_language():
    with pytest.raises(ValidationError):
        ChatRequest(message="hello", language="de")


def test_chat_request_rejects_oversized_payload():
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 10_001)


def test_chat_response_from_full_result():
    result = ChatResult(
        session_id="s1", language="en", reply="Answer", urgency_level=3,
        recommendation=("Book an appointment.", "Within 24-48 hours"),
        follow_up_questions=["How long?"],
        sources=[Source("NHS: Headaches", "https://www.nhs.uk/conditions/headaches/", "snippet")],
        safety_status="flagged", safety_flags=["medication_request"], safety_messages=["No prescriptions."],
        disclaimer="Not medical advice.",
    )
    response = ChatResponse.from_result(result)
    assert response.recommendation.text == "Book an appointment."
    assert response.recommendation.timeframe == "Within 24-48 hours"
    assert response.sources[0].model_dump() == {"title": "NHS: Headaches", "url": "https://www.nhs.uk/conditions/headaches/"}
    assert response.safety_status.status == "flagged"
    assert response.safety_status.flags == ["medication_request"]


def test_chat_response_from_blocked_result():
    result = ChatResult("s1", "fr", "Pouvez-vous préciser ?", 1, safety_status="blocked",
                        safety_flags=["too_short"], safety_messages=["Pouvez-vous préciser ?"])
    response = ChatResponse.from_result(result)
    assert response.recommendation is None
    assert response.sources == []
    assert response.disclaimer is None


def test_urgency_level_must_be_between_1_and_5():
    with pytest.raises(ValidationError):
        ChatResponse(session_id="s1", language="en", reply="x", urgency_level=6,
                     safety_status={"status": "ok"})
