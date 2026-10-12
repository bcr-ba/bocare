import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop import config_loader
from desktop.api_client import ApiError, BocareApiClient
from desktop.theme import urgency_kind
from desktop.widgets import (
    AssistantCard,
    ChatInput,
    ChatView,
    ErrorBubble,
    MessageRow,
    PendingCard,
    Suggestions,
    TypingIndicator,
    assistant_bubble,
    set_style_property,
    user_bubble,
)

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def format_reply(response: Dict[str, Any]) -> str:
    """Plain Markdown version of a /chat response, used for the exported transcript."""
    recommendation = response.get("recommendation")
    if not recommendation:  # blocked input, small talk or server-side error: just the message
        return response["reply"]

    t = config_loader.strings()[response["language"]]
    level = response["urgency_level"]
    triage = (f"**{t['urgency']} {level}/5 ({t['urgency_labels'][level]})**  \n"
              f"**{t['recommendation']}** {recommendation['text']}  \n"
              f"**{t['timeframe']}** {recommendation['timeframe']}")

    parts = [f"**{message}**" for message in response["safety_status"]["messages"]]
    urgent = level >= config_loader.settings().high_urgency_level
    parts += [triage, response["reply"]] if urgent else [response["reply"], triage]
    if response["follow_up_questions"]:
        parts.append(f"**{t['follow_up']}**\n\n" + "\n".join(f"- {q}" for q in response["follow_up_questions"]))
    if response["sources"]:
        links = "\n".join(f"- [{s['title']}]({s['url']})" for s in response["sources"])
        parts.append(f"**{t['sources']}**\n\n{links}")
    if response.get("disclaimer"):
        parts.append(f"*{response['disclaimer']}*")
    return "\n\n".join(parts)


def now() -> str:
    return datetime.now().strftime("%H:%M")


class ResponseThread(QThread):
    """Streams one reply from the API off the UI thread."""
    preview_ready = pyqtSignal(object)  # triage and recommendation, before the model answers
    sources_ready = pyqtSignal(object)
    stage_changed = pyqtSignal(str)
    response_ready = pyqtSignal(object)  # the full, verified reply
    failed = pyqtSignal(str)

    def __init__(self, client: BocareApiClient, message: str, language: str, session_id: Optional[str],
                 generation: int):
        super().__init__()
        self.client = client
        self.message = message
        self.language = language
        self.session_id = session_id
        self.generation = generation  # which consultation this request belongs to

    def run(self):
        signals = {"triage": self.preview_ready, "sources": self.sources_ready, "done": self.response_ready}
        try:
            for event, data in self.client.chat_stream(self.message, self.language, self.session_id):
                if event == "status":
                    self.stage_changed.emit(data["stage"])
                elif event in signals:
                    signals[event].emit(data)
                    if event == "done":
                        return
            self.failed.emit("The server closed the stream before answering.")
        except ApiError as exc:
            self.failed.emit(str(exc))


class HealthThread(QThread):
    checked = pyqtSignal(object)  # the /health payload, or None when the server is unreachable

    def __init__(self, client: BocareApiClient):
        super().__init__()
        self.client = client

    def run(self):
        try:
            self.checked.emit(self.client.health())
        except ApiError:
            self.checked.emit(None)


class MedicalChatbotApp(QMainWindow):
    def __init__(self, client: BocareApiClient):
        super().__init__()
        self.client = client
        self.settings = QSettings("BoCare", "MedicalChatbot")
        self.language = self.settings.value("language", "fr")
        self.session_id: Optional[str] = None
        self.transcript: List[Dict[str, Any]] = []
        self.session_level: Optional[int] = None
        self.connection = "checking"
        self._generation = 0
        self._last_message: Optional[str] = None
        self._typing_row: Optional[MessageRow] = None
        self._pending_row: Optional[MessageRow] = None
        self._error_row: Optional[MessageRow] = None
        self._suggestions: Optional[Suggestions] = None
        self.response_thread: Optional[ResponseThread] = None
        self.health_thread: Optional[HealthThread] = None

        settings = config_loader.settings()
        self.setMinimumSize(*settings.window_min_size)
        self.resize(*settings.window_default_size)
        self.setStyleSheet(config_loader.stylesheet())
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(config_loader.colors()["accent_hover"]))
        self.setPalette(palette)
        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        self._build_ui()
        self._apply_language()
        self.start_new_session()
        self.check_health()

    @property
    def strings(self) -> Dict[str, Any]:
        return config_loader.strings()[self.language]

    @property
    def busy(self) -> bool:
        return self._typing_row is not None or self._pending_row is not None

    # ---- layout -------------------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        self.chat = ChatView()
        layout.addWidget(self.chat, 1)
        layout.addWidget(self._build_composer())

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        row = QHBoxLayout(header)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(12)

        if LOGO_PATH.exists():
            logo = QLabel()
            pixmap = QPixmap(str(LOGO_PATH))
            logo.setPixmap(pixmap.scaledToHeight(config_loader.settings().logo_height,
                                                 Qt.TransformationMode.SmoothTransformation))
            row.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("BoCare")
        title.setObjectName("AppTitle")
        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(self.subtitle_label)
        row.addLayout(titles)
        row.addStretch(1)

        self.level_pill = QLabel()
        self.level_pill.setObjectName("Pill")
        self.connection_pill = QLabel()
        self.connection_pill.setObjectName("Pill")
        row.addWidget(self.level_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.connection_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        segment = QHBoxLayout()
        segment.setSpacing(0)
        self.language_group = QButtonGroup(self)
        self.language_buttons: Dict[str, QPushButton] = {}
        for code, position in (("fr", "left"), ("en", "right")):
            button = QPushButton(code.upper())
            button.setObjectName("SegmentButton")
            button.setProperty("position", position)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, c=code: self.change_language(c))
            self.language_group.addButton(button)
            self.language_buttons[code] = button
            segment.addWidget(button)
        row.addLayout(segment)

        self.new_session_btn = QPushButton()
        self.new_session_btn.setObjectName("SecondaryButton")
        self.new_session_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_session_btn.clicked.connect(self.start_new_session)
        row.addWidget(self.new_session_btn)
        return header

    def _build_composer(self) -> QFrame:
        composer = QFrame()
        composer.setObjectName("Composer")
        layout = QVBoxLayout(composer)
        layout.setContentsMargins(20, 12, 20, 10)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.input_box = ChatInput()
        self.input_box.submitted.connect(self.send_message)
        self.input_box.textChanged.connect(self._update_counter)
        self.send_button = QPushButton()
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self.send_message)
        row.addWidget(self.input_box, 1)
        row.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(row)

        meta = QHBoxLayout()
        self.emergency_label = QLabel()
        self.emergency_label.setObjectName("EmergencyBar")
        self.hint_label = QLabel()
        self.hint_label.setObjectName("Hint")
        self.counter_label = QLabel()
        self.counter_label.setObjectName("Counter")
        meta.addWidget(self.emergency_label)
        meta.addStretch(1)
        meta.addWidget(self.hint_label)
        meta.addWidget(self.counter_label)
        layout.addLayout(meta)
        return composer

    def _build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.clear()
        file_menu = menu_bar.addMenu(self.strings["menu_file"])
        for label, handler, shortcut in [
            (self.strings["new_session"], self.start_new_session, "Ctrl+N"),
            (self.strings["export"], self.export_session, "Ctrl+E"),
            (self.strings["quit"], self.close, "Ctrl+Q"),
        ]:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(handler)
            file_menu.addAction(action)
        help_menu = menu_bar.addMenu(self.strings["menu_help"])
        about = QAction(self.strings["about"], self)
        about.triggered.connect(lambda: QMessageBox.about(self, self.strings["about"], self.strings["about_text"]))
        help_menu.addAction(about)

    # ---- language and status ------------------------------------------------------------------

    def _apply_language(self):
        s = self.strings
        self.setWindowTitle(s["window_title"])
        self.subtitle_label.setText(s["subtitle"])
        self.new_session_btn.setText(s["new_session"])
        self.send_button.setText(s["send"])
        self.input_box.setPlaceholderText(s["placeholder"])
        self.hint_label.setText(s["hint"])
        danger = config_loader.colors()["danger"]
        self.emergency_label.setText(f'<span style="color:{danger}">●</span>&nbsp; {s["emergency_bar"]}')
        self.language_buttons[self.language].setChecked(True)
        self._render_connection()
        self._render_level()
        self._build_menu()
        if self._suggestions is not None:
            self._show_suggestions()

    def change_language(self, language: str):
        if language == self.language:
            return
        self.language = language
        self.settings.setValue("language", language)
        self._apply_language()

    def _render_connection(self):
        kind = {"connected": "ok", "ai_unavailable": "warn", "offline": "error"}.get(self.connection, "")
        self.connection_pill.setText(f"● {self.strings[self.connection]}")
        set_style_property(self.connection_pill, "kind", kind)

    def _render_level(self):
        self.level_pill.setVisible(self.session_level is not None)
        if self.session_level is not None:
            label = self.strings["urgency_labels"][self.session_level]
            self.level_pill.setText(self.strings["level_pill"].format(level=self.session_level, label=label))
            set_style_property(self.level_pill, "kind", urgency_kind(self.session_level))

    def _set_connection(self, state: str):
        self.connection = state
        self._render_connection()

    def check_health(self):
        self.health_thread = HealthThread(self.client)
        self.health_thread.checked.connect(self._on_health)
        self.health_thread.start()

    def _on_health(self, payload: Optional[Dict[str, Any]]):
        if payload is None:
            self._set_connection("offline")
        else:
            self._set_connection("connected" if payload.get("llm_configured") else "ai_unavailable")

    # ---- conversation -------------------------------------------------------------------------

    def start_new_session(self):
        self._generation += 1  # replies to the previous consultation are ignored
        self.session_id = None
        self.transcript = []
        self.session_level = None
        self._render_level()
        self._typing_row = self._pending_row = self._error_row = None
        self.chat.clear()
        self._suggestions = None
        self._set_busy(False)
        self.chat.add(MessageRow(assistant_bubble(self.strings["welcome"]), from_user=False))
        self._record("assistant", self.strings["welcome"])
        self._show_suggestions()
        self.input_box.setFocus()

    def _show_suggestions(self):
        self.chat.remove(self._suggestions)
        self._suggestions = Suggestions(self.strings["suggestions_title"], self.strings["suggestions"])
        self._suggestions.picked.connect(self.send_text)
        self.chat.add(self._suggestions)

    def _record(self, role: str, text: str):
        self.transcript.append({"role": role, "text": text, "time": datetime.now().isoformat(timespec="seconds")})

    def add_user_message(self, text: str):
        self.chat.add(MessageRow(user_bubble(text), from_user=True, meta=now()))
        self._record("user", text)

    def send_message(self):
        text = self.input_box.toPlainText().strip()
        if not text or self.busy or len(text) > config_loader.settings().max_input_length:
            return
        self.input_box.clear()
        self.send_text(text)

    def send_text(self, text: str, show_user_message: bool = True):
        if self.busy:
            return
        self.chat.remove(self._suggestions)
        self._suggestions = None
        self.chat.remove(self._error_row)
        self._error_row = None
        if show_user_message:
            self.add_user_message(text)
        self._last_message = text

        self._set_busy(True)
        self.response_thread = ResponseThread(self.client, text, self.language, self.session_id, self._generation)
        self.response_thread.preview_ready.connect(self.handle_preview)
        self.response_thread.sources_ready.connect(self.handle_sources)
        self.response_thread.stage_changed.connect(self.handle_stage)
        self.response_thread.response_ready.connect(self.handle_response)
        self.response_thread.failed.connect(self.handle_failure)
        self.response_thread.start()

    def _is_stale(self) -> bool:
        thread = self.sender()
        return isinstance(thread, ResponseThread) and thread.generation != self._generation

    def handle_preview(self, preview: Dict[str, Any]):
        """Triage arrived: show it now, the explanation follows once verified."""
        if self._is_stale():
            return
        started = self._typing_row.content.started if self._typing_row else None
        self._remove_typing()
        self.session_id = preview["session_id"]
        self.session_level = preview["urgency_level"]
        self._render_level()
        strings = config_loader.strings()[preview["language"]]
        card = PendingCard(preview, strings, strings["stage_retrieving"], started)
        self._pending_row = self.chat.add(MessageRow(card, from_user=False))

    def handle_sources(self, sources: List[Dict[str, str]]):
        if not self._is_stale() and self._pending_row is not None:
            self._pending_row.content.set_sources(sources)

    def handle_stage(self, stage: str):
        if self._is_stale() or self._pending_row is None:
            return
        strings = self._pending_row.content.strings
        self._pending_row.content.set_stage(strings.get(f"stage_{stage}", strings["typing"]))

    def handle_response(self, response: Dict[str, Any]):
        if self._is_stale():
            return
        self._set_busy(False)
        self.session_id = response["session_id"]
        if self.connection == "offline":
            self._set_connection("connected")

        if response.get("recommendation"):
            content = AssistantCard(response, config_loader.strings()[response["language"]])
            self.session_level = response["urgency_level"]
            self._render_level()
        else:
            content = assistant_bubble(response["reply"], notice=response["safety_status"]["status"] == "blocked")
        self.chat.add(MessageRow(content, from_user=False, meta=now()))
        self._record("assistant", format_reply(response))
        self.input_box.setFocus()

    def handle_failure(self, error: str):
        if self._is_stale():
            return
        self._set_busy(False)
        self._set_connection("offline")
        bubble = ErrorBubble(self.strings["server_error"].format(error=error), self.strings["retry"])
        bubble.retry_clicked.connect(self._retry)
        self._error_row = self.chat.add(MessageRow(bubble, from_user=False, meta=now()))

    def _retry(self):
        if self._last_message:
            self.send_text(self._last_message, show_user_message=False)

    def _set_busy(self, busy: bool):
        if busy and not self.busy:
            self._typing_row = self.chat.add(MessageRow(TypingIndicator(self.strings["typing"]), from_user=False))
        elif not busy:
            self._remove_typing()
            if self._pending_row is not None:
                self._pending_row.content.stop()
                self.chat.remove(self._pending_row)
                self._pending_row = None
        self._update_counter()

    def _remove_typing(self):
        if self._typing_row is not None:
            self._typing_row.content.stop()
            self.chat.remove(self._typing_row)
            self._typing_row = None

    def _update_counter(self):
        settings = config_loader.settings()
        length = len(self.input_box.toPlainText())
        over = length > settings.max_input_length
        self.counter_label.setVisible(length > settings.max_input_length * settings.counter_from_ratio)
        self.counter_label.setText(f"{length}/{settings.max_input_length}")
        set_style_property(self.counter_label, "over", "true" if over else "false")
        self.send_button.setEnabled(not self.busy and not over)

    # ---- export -------------------------------------------------------------------------------

    def export_session(self):
        name = f"bocare_session_{(self.session_id or 'new')[:8]}.json"
        path, _ = QFileDialog.getSaveFileName(self, self.strings["export"], name, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"session_id": self.session_id, "messages": self.transcript}, f,
                          indent=2, ensure_ascii=False)
        except OSError as exc:
            QMessageBox.warning(self, self.strings["error"], self.strings["export_failed"].format(error=exc))
            return
        QMessageBox.information(self, self.strings["export"], self.strings["exported"].format(path=path))
