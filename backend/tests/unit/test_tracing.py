import pytest
from conftest import FakeLLM, FakeRetriever
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.pipeline.orchestrator import Orchestrator
from app.pipeline.responder import Responder

_EXPORTER = InMemorySpanExporter()
_provider = TracerProvider()
_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
trace.set_tracer_provider(_provider)  # the global provider can only be set once per process

PATIENT_TEXT = "Zorglub chest pain since my wedding"
MODEL_TEXT = "Glorbex: chest pain can signal a heart problem."


@pytest.fixture
def spans():
    _EXPORTER.clear()
    yield lambda: {s.name: s for s in _EXPORTER.get_finished_spans()}
    _EXPORTER.clear()


@pytest.fixture
def orchestrator():
    return Orchestrator(Responder(FakeRetriever(), FakeLLM(reply=MODEL_TEXT)))


def test_a_turn_is_one_tree_of_spans(orchestrator, spans):
    orchestrator.handle(PATIENT_TEXT, language="en", request_id="req-1")
    by_name = spans()
    turn = by_name["chat.turn"]
    for child in ("safety.validate", "triage.assess", "retrieval.search", "answer.generate", "answer.verify"):
        assert by_name[child].parent.span_id == turn.context.span_id, child
        assert by_name[child].context.trace_id == turn.context.trace_id


def test_turn_records_the_outcome(orchestrator, spans):
    orchestrator.handle(PATIENT_TEXT, language="en", request_id="req-1")
    attributes = spans()["chat.turn"].attributes
    assert attributes["bocare.request_id"] == "req-1"
    assert attributes["bocare.urgency_level"] == 5
    assert attributes["bocare.verification"] == "passed"
    assert attributes["bocare.sources"] == 1
    assert spans()["triage.assess"].attributes["triage.urgency"] == 5


def test_streaming_keeps_all_steps_in_one_trace(orchestrator, spans):
    events = [name for name, _ in orchestrator.stream(PATIENT_TEXT, language="en", request_id="req-2")]
    assert events[0] == "triage" and events[-1] == "done"
    finished = _EXPORTER.get_finished_spans()
    turn = next(s for s in finished if s.name == "chat.turn")
    assert {s.context.trace_id for s in finished} == {turn.context.trace_id}
    assert all(s.parent.span_id == turn.context.span_id for s in finished if s.name != "chat.turn")
    assert turn.attributes["bocare.endpoint"] == "chat/stream"


def test_spans_never_contain_patient_or_model_text(orchestrator, spans):
    orchestrator.handle(PATIENT_TEXT, language="en")
    list(orchestrator.stream(PATIENT_TEXT, language="en"))
    for s in _EXPORTER.get_finished_spans():
        for key, value in s.attributes.items():
            text = " ".join(map(str, value)) if isinstance(value, tuple) else str(value)
            assert "Zorglub" not in text and "Glorbex" not in text, f"{s.name}.{key} leaks text"
        assert all("Zorglub" not in str(e.attributes) for e in s.events)


def test_errors_are_recorded_on_the_turn(orchestrator, spans, monkeypatch):
    monkeypatch.setattr(orchestrator.responder, "respond", lambda *a, **k: 1 / 0)
    orchestrator.handle(PATIENT_TEXT, language="en")
    turn = spans()["chat.turn"]
    assert turn.status.status_code == trace.StatusCode.ERROR
    assert any(e.name == "exception" for e in turn.events)
