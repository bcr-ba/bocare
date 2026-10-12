"""Chat building blocks: message rows, the structured assistant card, typing indicator and input box."""
import html
import time
from typing import Any, Dict, List, Optional

import markdown2
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QTextOption
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from desktop import config_loader
from desktop.theme import urgency_kind


def markdown_html(text: str) -> str:
    return markdown2.markdown(text, extras={"breaks": {"on_newline": True}, "cuddled-lists": None})


def text_label(content: str, object_name: str = "") -> QLabel:
    """Word-wrapped rich-text label with selectable text and clickable links."""
    label = QLabel(content)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    if object_name:
        label.setObjectName(object_name)
    return label


def set_style_property(widget: QWidget, name: str, value: Any) -> None:
    """Set a property used by the stylesheet and re-apply the style."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def link(url: str, title: str) -> str:
    color = config_loader.colors()["accent_hover"]
    return f'<a href="{html.escape(url)}" style="color:{color}">{html.escape(title)}</a>'


class MessageRow(QWidget):
    """One message in the chat: content aligned left (assistant) or right (user), with a timestamp."""

    def __init__(self, content: QWidget, from_user: bool, meta: str = ""):
        super().__init__()
        self.content = content
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(content)
        if meta:
            stamp = QLabel(meta)
            stamp.setObjectName("Timestamp")
            stamp.setAlignment(Qt.AlignmentFlag.AlignRight if from_user else Qt.AlignmentFlag.AlignLeft)
            column.addWidget(stamp)

        # Stretch factors instead of alignment flags: aligned word-wrapped labels get clipped heights in Qt.
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 6, 20, 6)
        if from_user:
            row.addStretch(1)
            row.addLayout(column)
        else:
            row.addLayout(column, 3)
            row.addStretch(1)

    def set_max_width(self, width: int) -> None:
        self.content.setMaximumWidth(width)


class TriagePanel(QFrame):
    def __init__(self, level: int, recommendation: Dict[str, str], strings: Dict[str, Any]):
        super().__init__()
        self.setObjectName("Triage")
        self.setProperty("kind", urgency_kind(level))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        badge = QLabel(f"{strings['triage_title']} · {level}/5 · {strings['urgency_labels'][level]}".upper())
        badge.setObjectName("TriageBadge")
        timeframe = QLabel(f"{strings['timeframe']} {recommendation['timeframe']}")
        timeframe.setObjectName("Muted")
        top.addWidget(badge)
        top.addStretch(1)
        top.addWidget(timeframe)

        layout.addLayout(top)
        layout.addWidget(text_label(html.escape(recommendation["text"]), "TriageAdvice"))


def section_title(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


def add_safety_banners(layout: QVBoxLayout, safety: Dict[str, Any]) -> None:
    for flag, message in zip(safety["flags"], safety["messages"]):
        banner = text_label(html.escape(message), "Banner")
        banner.setProperty("kind", "danger" if flag == "self_harm" else "warn")
        layout.addWidget(banner)


def sources_label(sources: List[Dict[str, str]]) -> QLabel:
    return text_label("<br>".join(f"{i}.&nbsp; {link(s['url'], s['title'])}" for i, s in enumerate(sources, 1)))


def bullet_list(items: List[str]) -> str:
    return "<br>".join(f"•&nbsp; {item}" for item in items)


def structured_answer(answer: Dict[str, Any], sources: List[Dict[str, str]], strings: Dict[str, Any]) -> QWidget:
    """Summary, explanations with clickable citation numbers, warning signs, self-care, question."""
    def cite(ids: List[int]) -> str:
        links = [link(sources[i - 1]["url"], str(i)) for i in ids if 1 <= i <= len(sources)]
        return f" <sup>[{', '.join(links)}]</sup>" if links else ""

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(text_label(html.escape(answer["summary"])))
    sections = [
        (strings["explanations_title"],
         [html.escape(e["text"]) + cite(e.get("source_ids", [])) for e in answer.get("possible_explanations", [])]),
        (strings["warning_signs_title"], [html.escape(t) for t in answer.get("warning_signs", [])]),
        (strings["self_care_title"], [html.escape(t) for t in answer.get("self_care", [])]),
    ]
    for title, items in sections:
        if items:
            layout.addWidget(section_title(title))
            layout.addWidget(text_label(bullet_list(items)))
    if answer.get("clarifying_question"):
        layout.addWidget(text_label(f"<i>{html.escape(answer['clarifying_question'])}</i>", "Question"))
    return container


class AssistantCard(QFrame):
    """A full /chat reply: safety banners, triage, answer, follow-up questions, sources, disclaimer."""

    def __init__(self, response: Dict[str, Any], strings: Dict[str, Any]):
        super().__init__()
        self.setObjectName("AssistantCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        add_safety_banners(layout, response["safety_status"])

        level = response["urgency_level"]
        sources = response.get("sources") or []
        triage = TriagePanel(level, response["recommendation"], strings)
        structured = response.get("answer")
        answer = (structured_answer(structured, sources, strings) if structured
                  else text_label(markdown_html(response["reply"])))
        # Urgent advice comes before the explanation.
        for block in ([triage, answer] if level >= 4 else [answer, triage]):
            layout.addWidget(block)

        questions = response.get("follow_up_questions") or []
        if questions:
            layout.addWidget(section_title(strings["follow_up_title"]))
            layout.addWidget(text_label(bullet_list([html.escape(q) for q in questions])))

        if sources:
            layout.addWidget(section_title(strings["sources_title"]))
            layout.addWidget(sources_label(sources))

        if response.get("disclaimer"):
            layout.addWidget(text_label(html.escape(response["disclaimer"]), "Muted"))


def assistant_bubble(markdown_text: str, notice: bool = False) -> QLabel:
    return text_label(markdown_html(markdown_text), "NoticeBubble" if notice else "AssistantBubble")


def user_bubble(text: str) -> QLabel:
    return text_label(html.escape(text).replace("\n", "<br>"), "UserBubble")


class ErrorBubble(QFrame):
    retry_clicked = pyqtSignal()

    def __init__(self, markdown_text: str, retry_label: str):
        super().__init__()
        self.setObjectName("ErrorBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(text_label(markdown_html(markdown_text), "ErrorText"))
        button = QPushButton(retry_label)
        button.setObjectName("SecondaryButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.retry_clicked)
        buttons = QHBoxLayout()
        buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)


class TypingIndicator(QLabel):
    """'BoCare is analysing your message...  12 s' with animated dots and elapsed time,
    since a local model can take half a minute."""

    def __init__(self, text: str, object_name: str = "TypingBubble", started: Optional[float] = None):
        super().__init__()
        self.setObjectName(object_name)
        self._text = text
        self.started = started or time.monotonic()
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(config_loader.settings().progress_refresh_ms)
        self._refresh()

    def _refresh(self) -> None:
        self._tick = (self._tick + 1) % 4
        elapsed = int(time.monotonic() - self.started)
        self.setText(f"{self._text}{'.' * self._tick}{' ' * (3 - self._tick)}   {elapsed} s")

    def set_text(self, text: str) -> None:
        self._text = text
        self._refresh()

    def stop(self) -> None:
        self._timer.stop()


class PendingCard(QFrame):
    """Shown while the explanation is being written: the triage and safety messages (which don't
    need the model) right away, a progress line, and the sources once they are retrieved."""

    def __init__(self, preview: Dict[str, Any], strings: Dict[str, Any], stage_text: str,
                 started: Optional[float] = None):
        super().__init__()
        self.setObjectName("AssistantCard")
        self.strings = strings
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(10)
        add_safety_banners(self._layout, preview["safety_status"])
        self._layout.addWidget(TriagePanel(preview["urgency_level"], preview["recommendation"], strings))
        self.progress = TypingIndicator(stage_text, "InlineProgress", started)
        self._layout.addWidget(self.progress)

    def set_stage(self, text: str) -> None:
        self.progress.set_text(text)

    def set_sources(self, sources: List[Dict[str, str]]) -> None:
        if sources:
            self._layout.addWidget(section_title(self.strings["sources_title"]))
            self._layout.addWidget(sources_label(sources))

    def stop(self) -> None:
        self.progress.stop()


class Suggestions(QWidget):
    picked = pyqtSignal(str)

    def __init__(self, title: str, items: List[str]):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 4, 20, 8)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("SuggestionsTitle")
        layout.addWidget(heading)
        for item in items:
            chip = QPushButton(item)
            chip.setObjectName("Chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _checked=False, text=item: self.picked.emit(text))
            layout.addWidget(chip, alignment=Qt.AlignmentFlag.AlignLeft)

    def set_max_width(self, width: int) -> None:
        pass


class ChatInput(QPlainTextEdit):
    """Enter sends, Shift+Enter inserts a new line; grows from one to six lines."""
    submitted = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.max_lines = config_loader.settings().input_max_lines
        self.setObjectName("InputBox")
        self.setTabChangesFocus(True)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)
        self._fit_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Qt would insert U+2028 (line separator); send a plain newline instead.
                self.insertPlainText("\n")
            else:
                self.submitted.emit()
            return
        super().keyPressEvent(event)

    def _fit_height(self, *_args) -> None:
        lines = max(1, min(int(self.document().size().height()), self.max_lines))
        margins = self.contentsMargins()
        height = (lines * self.fontMetrics().lineSpacing() + int(self.document().documentMargin() * 2)
                  + margins.top() + margins.bottom() + 14)
        self.setFixedHeight(height)
        # Only show a scrollbar once the box has reached its maximum height.
        overflowing = self.document().size().height() > self.max_lines
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if overflowing else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class ChatView(QScrollArea):
    """Scrollable message list that keeps the newest message in view."""

    def __init__(self):
        super().__init__()
        self.setObjectName("ChatView")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("ChatContent")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 12, 0, 12)
        self._layout.setSpacing(2)
        self._layout.addStretch(1)
        self.setWidget(content)
        scrollbar = self.verticalScrollBar()
        scrollbar.rangeChanged.connect(lambda _minimum, maximum: scrollbar.setValue(maximum))

    def bubble_width(self) -> int:
        settings = config_loader.settings()
        return min(settings.bubble_max_width, int(self.viewport().width() * settings.bubble_width_ratio))

    def add(self, row: QWidget) -> QWidget:
        self._layout.insertWidget(self._layout.count() - 1, row)
        row.set_max_width(self.bubble_width())
        return row

    def remove(self, row: Optional[QWidget]) -> None:
        if row is not None:
            self._layout.removeWidget(row)
            row.hide()  # deleteLater only runs on the next event-loop pass; don't leave it drawn until then
            row.deleteLater()

    def clear(self) -> None:
        while self._layout.count() > 1:
            widget = self._layout.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = self.bubble_width()
        for i in range(self._layout.count() - 1):
            widget = self._layout.itemAt(i).widget()
            if widget:
                widget.set_max_width(width)
