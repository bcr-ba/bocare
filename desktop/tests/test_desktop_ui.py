import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

from desktop.config_loader import settings, strings  # noqa: E402
from desktop.ui_main import MedicalChatbotApp, format_reply  # noqa: E402
from desktop.widgets import AssistantCard, ChatInput, ErrorBubble, TriagePanel  # noqa: E402

APP = QApplication.instance() or QApplication([])

EMERGENCY = {
    "session_id": "s1", "language": "en", "reply": "Chest pain needs urgent care.", "urgency_level": 5,
    "recommendation": {"text": "Call 15 or 112 now.", "timeframe": "Immediately"},
    "follow_up_questions": ["How long have you had these symptoms?"],
    "sources": [{"title": "NHS: Chest pain", "url": "https://www.nhs.uk/conditions/chest-pain/"}],
    "safety_status": {"status": "ok", "flags": [], "messages": []}, "disclaimer": "Not medical advice.",
}
LOW = dict(EMERGENCY, urgency_level=1, recommendation={"text": "Monitor.", "timeframe": "Monitor"})


class FakeClient:
    def health(self):
        return {"status": "ok", "llm_configured": True}

    def chat(self, *args, **kwargs):
        raise AssertionError("tests call handle_response directly")


@pytest.fixture
def window():
    w = MedicalChatbotApp(FakeClient())
    w.health_thread.wait()
    w.language = "en"
    w._apply_language()
    yield w
    w.close()


def test_emergency_card_puts_triage_before_the_answer():
    card = AssistantCard(EMERGENCY, strings()["en"])
    layout = card.layout()
    assert isinstance(layout.itemAt(0).widget(), TriagePanel)
    assert layout.itemAt(0).widget().property("kind") == "high"


def test_low_urgency_card_puts_the_answer_first():
    card = AssistantCard(LOW, strings()["en"])
    assert isinstance(card.layout().itemAt(1).widget(), TriagePanel)
    assert card.layout().itemAt(1).widget().property("kind") == "low"


def test_self_harm_banner_is_styled_as_danger():
    response = dict(LOW, safety_status={"status": "flagged", "flags": ["self_harm"], "messages": ["Call 3114."]})
    card = AssistantCard(response, strings()["en"])
    banner = card.layout().itemAt(0).widget()
    assert banner.objectName() == "Banner" and banner.property("kind") == "danger"


def test_response_updates_session_and_level_pill(window):
    window.handle_response(EMERGENCY)
    assert window.session_id == "s1"
    assert not window.level_pill.isHidden()
    assert window.level_pill.text() == "Level 5/5 · emergency"
    assert window.level_pill.property("kind") == "high"


def test_new_session_resets_state(window):
    window.handle_response(EMERGENCY)
    window.start_new_session()
    assert window.session_id is None and window.session_level is None
    assert window.level_pill.isHidden()


def test_failure_shows_retry_and_marks_offline(window):
    window._last_message = "I have chest pain"
    window.handle_failure("Cannot reach the BoCare API")
    assert window.connection == "offline"
    assert window._error_row is not None and isinstance(window._error_row.content, ErrorBubble)


def test_counter_blocks_overlong_messages(window):
    window.input_box.setPlainText("x" * (settings().max_input_length + 1))
    assert not window.send_button.isEnabled()
    assert window.counter_label.property("over") == "true"
    window.input_box.setPlainText("short")
    assert window.send_button.isEnabled()


def test_enter_submits_and_shift_enter_adds_a_line():
    box = ChatInput()
    submitted = []
    box.submitted.connect(lambda: submitted.append(True))
    box.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert submitted == [True]
    box.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier))
    assert submitted == [True]
    assert box.document().blockCount() == 2


def test_exported_transcript_keeps_lists_as_markdown_lists():
    text = format_reply(EMERGENCY)
    assert "**To guide you better:**\n\n- How long have you had these symptoms?" in text
    assert text.index("Call 15 or 112 now.") < text.index("Chest pain needs urgent care.")


STRUCTURED = dict(EMERGENCY, answer={
    "summary": "Chest pain spreading to the arm can signal a heart attack.",
    "possible_explanations": [{"text": "Heart attack", "source_ids": [1]}],
    "warning_signs": ["Shortness of breath"], "self_care": [], "clarifying_question": "When did it start?"},
    verification={"status": "passed", "failed_checks": []})


def test_structured_answer_renders_sections_and_citation_links():
    card = AssistantCard(STRUCTURED, strings()["en"])
    texts = " ".join(label.text() for label in card.findChildren(QLabel))
    assert "POSSIBLE EXPLANATIONS" in texts and "WARNING SIGNS" in texts
    assert 'href="https://www.nhs.uk/conditions/chest-pain/"' in texts  # [1] links to source 1
    assert "When did it start?" in texts


def test_preview_shows_triage_before_the_answer_arrives(window):
    window._set_busy(True)
    window.handle_preview(dict(EMERGENCY, reply="", verification={"status": "pending", "failed_checks": []}))
    assert window._pending_row is not None and window._typing_row is None
    assert window.level_pill.text() == "Level 5/5 · emergency"  # shown before the model answers
    window.handle_stage("verifying")
    assert "Checking the answer" in window._pending_row.content.progress.text()
    window.handle_response(STRUCTURED)
    assert window._pending_row is None and not window.busy


def test_stream_client_parses_server_sent_events(monkeypatch):
    import requests

    from desktop.api_client import BocareApiClient

    class FakeStream:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_lines(self, decode_unicode=True):
            yield from ['event: triage', 'data: {"urgency_level": 5}', '',
                        'event: status', 'data: {"stage": "generating"}', '',
                        'event: done', 'data: {"reply": "ok"}', '']

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeStream())
    events = list(BocareApiClient("http://x").chat_stream("hi", "en"))
    assert events == [("triage", {"urgency_level": 5}), ("status", {"stage": "generating"}), ("done", {"reply": "ok"})]
