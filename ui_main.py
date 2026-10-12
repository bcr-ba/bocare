from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QScrollArea, QMainWindow, QFrame, QSplitter, QMessageBox, QComboBox, QButtonGroup,
    QRadioButton, QGroupBox, QProgressBar, QStatusBar, QMenuBar, QMenu
)
from PyQt6.QtGui import QPixmap, QFont, QTextCursor, QIcon, QAction
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSettings
from chatbot_logic import global_chatbot
from datetime import datetime
import markdown2
import json


class ChatMessage(QFrame):
    """Individual chat message widget"""
    def __init__(self, message: str, is_user: bool = False, urgency_level: int = 1):
        super().__init__()
        self.setMaximumWidth(600)
        
        layout = QVBoxLayout()
        
        # Message content
        content = QTextEdit()
        content.setReadOnly(True)
        content.setHtml(markdown2.markdown(message))
        content.setMaximumHeight(200)
        content.setStyleSheet(self._get_message_style(is_user, urgency_level))
        
        # Timestamp
        timestamp = QLabel(datetime.now().strftime("%H:%M"))
        timestamp.setStyleSheet("color: #888; font-size: 11px;")
        timestamp.setAlignment(Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)
        
        layout.addWidget(content)
        layout.addWidget(timestamp)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.setLayout(layout)
        
        # Align message bubble
        if is_user:
            self.setStyleSheet("QFrame { margin-left: 50px; }")
        else:
            self.setStyleSheet("QFrame { margin-right: 50px; }")
    
    def _get_message_style(self, is_user: bool, urgency_level: int) -> str:
        if is_user:
            return """
                QTextEdit {
                    background-color: #00bfa5;
                    color: white;
                    border-radius: 15px;
                    padding: 10px;
                    border: none;
                }
            """
        else:
            # Color based on urgency
            if urgency_level >= 4:
                bg_color = "#ff5252"  # Red for high urgency
            elif urgency_level >= 3:
                bg_color = "#ff9800"  # Orange for medium urgency
            else:
                bg_color = "#2E2E2E"  # Default gray
                
            return f"""
                QTextEdit {{
                    background-color: {bg_color};
                    color: #E0E0E0;
                    border-radius: 15px;
                    padding: 10px;
                    border: none;
                }}
            """


class ResponseThread(QThread):
    """Thread for handling AI responses without blocking UI"""
    response_ready = pyqtSignal(str)
    
    def __init__(self, user_input: str, session_id: str = None):
        super().__init__()
        self.user_input = user_input
        self.session_id = session_id
    
    def run(self):
        try:
            response = global_chatbot.process_user_input(self.user_input, self.session_id)
            self.response_ready.emit(response)
        except Exception as e:
            self.response_ready.emit(f"⚠️ Une erreur s'est produite: {str(e)}")


class MedicalChatbotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_session_id = None
        self.conversation_history = []
        self.response_thread = None
        self.current_language = 'fr'  # Default language
        self.settings = QSettings('BoCare', 'MedicalChatbot')
        
        # Load saved language preference
        self.current_language = self.settings.value('language', 'fr')
        
        self.setWindowTitle("🏥 BoCare AI Assistant - Intelligent Medical Assistant")
        self.setMinimumSize(1000, 850)
        self.setWindowIcon(QIcon("assets/logo.png") if QPixmap("assets/logo.png").isNull() == False else QIcon())

        self.init_ui()
        self.init_menu_bar()
        self.update_language()
        self.start_new_session()

    def init_ui(self):
        font = QFont("Segoe UI", 10)
        self.setFont(font)

        # Main container
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
                color: #E0E0E0;
            }
            QWidget {
                background-color: #121212;
                color: #E0E0E0;
            }
            QLabel#Title {
                font-size: 24px;
                font-weight: bold;
                color: #1de9b6;
                padding: 10px;
            }
            QLabel#Subtitle {
                font-size: 14px;
                color: #B0B0B0;
                padding: 5px;
            }
            QTextEdit#InputBox {
                background-color: #1E1E1E;
                border: 2px solid #333;
                border-radius: 10px;
                padding: 10px;
                font-size: 14px;
                color: #E0E0E0;
                max-height: 100px;
            }
            QPushButton#SendButton {
                background-color: #00bfa5;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 12px 20px;
                border-radius: 8px;
                border: none;
            }
            QPushButton#SendButton:hover {
                background-color: #1de9b6;
            }
            QPushButton#SendButton:disabled {
                background-color: #555;
                color: #888;
            }
            QPushButton#NewSession {
                background-color: #333;
                color: #E0E0E0;
                font-size: 12px;
                padding: 8px 15px;
                border-radius: 6px;
                border: 1px solid #555;
            }
            QPushButton#NewSession:hover {
                background-color: #444;
            }
            QScrollArea {
                border: none;
                background-color: #1A1A1A;
            }
            QFrame#ChatArea {
                background-color: #1A1A1A;
                border-radius: 10px;
            }
        """)

        # Header section
        header_layout = QVBoxLayout()
        
        # Top control bar
        control_bar = QHBoxLayout()
        
        # Language selection
        lang_group = QGroupBox()
        lang_group.setObjectName("LanguageGroup")
        lang_layout = QHBoxLayout(lang_group)
        
        self.lang_fr = QRadioButton("🇫🇷 Français")
        self.lang_en = QRadioButton("🇬🇧 English")
        self.lang_fr.setChecked(self.current_language == 'fr')
        self.lang_en.setChecked(self.current_language == 'en')
        
        self.lang_fr.toggled.connect(lambda: self.change_language('fr'))
        self.lang_en.toggled.connect(lambda: self.change_language('en'))
        
        lang_layout.addWidget(self.lang_fr)
        lang_layout.addWidget(self.lang_en)
        
        control_bar.addWidget(lang_group)
        control_bar.addStretch()
        
        # New session button
        self.new_session_btn = QPushButton("🔄 Nouvelle Consultation")
        self.new_session_btn.setObjectName("NewSession")
        self.new_session_btn.clicked.connect(self.start_new_session)
        control_bar.addWidget(self.new_session_btn)
        
        header_layout.addLayout(control_bar)
        
        # Logo and title
        title_layout = QHBoxLayout()
        
        # Logo
        try:
            logo = QLabel()
            logo.setPixmap(QPixmap("assets/logo.png").scaledToWidth(80))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_layout.addWidget(logo)
        except:
            pass  # Skip logo if file not found
        
        # Title and subtitle
        title_text_layout = QVBoxLayout()
        self.title_label = QLabel("BoCare AI Assistant")
        self.title_label.setObjectName("Title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.subtitle_label = QLabel("Assistant médical intelligent avec IA conversationnelle et triage automatique")
        self.subtitle_label.setObjectName("Subtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_text_layout.addWidget(self.title_label)
        title_text_layout.addWidget(self.subtitle_label)
        title_layout.addLayout(title_text_layout)
        
        header_layout.addLayout(title_layout)
        main_layout.addLayout(header_layout)

        # Chat area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.chat_scroll.setWidget(self.chat_widget)
        main_layout.addWidget(self.chat_scroll, stretch=1)

        # Input section
        input_layout = QVBoxLayout()
        
        self.input_label = QLabel("💬 Décrivez vos symptômes ou posez votre question médicale :")
        self.input_label.setStyleSheet("color: #B0B0B0; font-size: 12px; padding: 5px;")
        input_layout.addWidget(self.input_label)
        
        # Input area with send button
        input_row = QHBoxLayout()
        
        self.input_box = QTextEdit()
        self.input_box.setObjectName("InputBox")
        self.input_box.setPlaceholderText("Ex: J'ai mal à la tête depuis 2 jours avec de la fièvre...")
        self.input_box.setMaximumHeight(100)
        
        self.send_button = QPushButton("📤 Envoyer")
        self.send_button.setObjectName("SendButton")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setFixedSize(120, 50)
        
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_button)
        
        input_layout.addLayout(input_row)
        
        # Progress bar for processing
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #333;
                border-radius: 5px;
                background-color: #1E1E1E;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #00bfa5;
                border-radius: 3px;
            }
        """)
        input_layout.addWidget(self.progress_bar)
        
        main_layout.addLayout(input_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("color: #888; font-size: 11px; padding: 5px; background-color: #1A1A1A;")
        self.status_bar.showMessage("✅ Prêt pour une nouvelle consultation")
        self.setStatusBar(self.status_bar)

        # Copyright
        copyright = QLabel("© 2025 Bocar Thierno Ousmane Ba - BoCare AI Assistant")
        copyright.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright.setStyleSheet("color: #555; font-size: 10px; padding: 5px;")
        main_layout.addWidget(copyright)

    def start_new_session(self):
        """Start a new consultation session"""
        try:
            welcome_message, session_id = global_chatbot.start_new_consultation(self.current_language)
            self.current_session_id = session_id
            
            # Clear chat history
            self.clear_chat_history()
            
            # Add welcome message
            self.add_message(welcome_message, is_user=False, urgency_level=1)
            
            # Update status
            status_msg = f"🆕 New consultation started - Session: {session_id[:8]}..." if self.current_language == 'en' else f"🆕 Nouvelle consultation démarrée - Session: {session_id[:8]}..."
            self.status_bar.showMessage(status_msg)
            
        except Exception as e:
            QMessageBox.warning(self, "Error" if self.current_language == 'en' else "Erreur", 
                              f"Unable to start new session: {str(e)}" if self.current_language == 'en' else f"Impossible de démarrer une nouvelle session: {str(e)}")

    def clear_chat_history(self):
        """Clear the chat display"""
        for i in reversed(range(self.chat_layout.count())):
            child = self.chat_layout.itemAt(i).widget()
            if child:
                child.setParent(None)

    def add_message(self, message: str, is_user: bool = False, urgency_level: int = 1):
        """Add a message to the chat display"""
        chat_message = ChatMessage(message, is_user, urgency_level)
        self.chat_layout.addWidget(chat_message)
        
        # Auto-scroll to bottom
        QTimer.singleShot(100, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        """Scroll chat area to bottom"""
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def send_message(self):
        """Send user message and get AI response"""
        user_input = self.input_box.toPlainText().strip()
        
        if not user_input:
            QMessageBox.information(self, "Information", "Veuillez saisir vos symptômes ou votre question.")
            return
        
        # Add user message to chat
        self.add_message(user_input, is_user=True)
        
        # Clear input box
        self.input_box.clear()
        
        # Disable send button and update status
        self.send_button.setEnabled(False)
        analyzing_text = "⏳ Analyzing..." if self.current_language == 'en' else "⏳ Analyse..."
        self.send_button.setText(analyzing_text)
        
        status_text = "🔄 Analysis in progress by medical AI..." if self.current_language == 'en' else "🔄 Analyse en cours par l'IA médicale..."
        self.status_bar.showMessage(status_text)
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        
        # Start response thread
        self.response_thread = ResponseThread(user_input, self.current_session_id)
        self.response_thread.response_ready.connect(self.handle_response)
        self.response_thread.start()

    def handle_response(self, response: str):
        """Handle AI response"""
        try:
            # Extract urgency level from localized banners (French & English)
            urgency_level = 1
            text_upper = response.upper()
            patterns = [
                (5, ["NIVEAU 5", "URGENCE IMMÉDIATE", "HIGH URGENCY LEVEL (5", "HIGH URGENCY LEVEL (5/5)", "NIVEAU D'URGENCE ÉLEVÉ (5"]),
                (4, ["NIVEAU 4", "NIVEAU D'URGENCE ÉLEVÉ (4", "HIGH URGENCY LEVEL (4", "CONSULTATION URGENTE"]),
                (3, ["NIVEAU 3", "NIVEAU D'URGENCE MODÉRÉ", "MODERATE URGENCY LEVEL (3", "SPÉCIALISÉE"]),
                (2, ["NIVEAU 2", "LOW URGENCY LEVEL (2", "FAIBLE (2"])
            ]
            for level, keys in patterns:
                if any(k.upper() in text_upper for k in keys):
                    urgency_level = level
                    break
            
            # Add AI response to chat
            self.add_message(response, is_user=False, urgency_level=urgency_level)
            
            # Update status based on urgency
            if urgency_level >= 4:
                status_text = f"🚨 ATTENTION: Emergency detected (Level {urgency_level}/5)" if self.current_language == 'en' else f"🚨 ATTENTION: Urgence détectée (Niveau {urgency_level}/5)"
            elif urgency_level >= 3:
                status_text = f"⚠️ Consultation recommended (Level {urgency_level}/5)" if self.current_language == 'en' else f"⚠️ Consultation recommandée (Niveau {urgency_level}/5)"
            else:
                status_text = f"💬 Consultation in progress (Level {urgency_level}/5)" if self.current_language == 'en' else f"💬 Consultation en cours (Niveau {urgency_level}/5)"
            
            self.status_bar.showMessage(status_text)
            
        except Exception as e:
            error_msg = f"⚠️ Processing error: {str(e)}" if self.current_language == 'en' else f"⚠️ Erreur lors du traitement: {str(e)}"
            self.add_message(error_msg, is_user=False, urgency_level=1)
            
            error_status = "❌ Analysis error" if self.current_language == 'en' else "❌ Erreur lors de l'analyse"
            self.status_bar.showMessage(error_status)
        
        finally:
            # Re-enable send button and hide progress
            self.send_button.setEnabled(True)
            send_text = "📤 Send" if self.current_language == 'en' else "📤 Envoyer"
            self.send_button.setText(send_text)
            self.progress_bar.setVisible(False)

    def init_menu_bar(self):
        """Initialize menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File' if self.current_language == 'en' else 'Fichier')
        
        new_session_action = QAction('New Consultation' if self.current_language == 'en' else 'Nouvelle Consultation', self)
        new_session_action.triggered.connect(self.start_new_session)
        file_menu.addAction(new_session_action)
        
        export_action = QAction('Export Session' if self.current_language == 'en' else 'Exporter Session', self)
        export_action.triggered.connect(self.export_session)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit' if self.current_language == 'en' else 'Quitter', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings menu
        settings_menu = menubar.addMenu('Settings' if self.current_language == 'en' else 'Paramètres')
        
        about_action = QAction('About' if self.current_language == 'en' else 'À propos', self)
        about_action.triggered.connect(self.show_about)
        settings_menu.addAction(about_action)
    
    def change_language(self, language):
        """Change application language"""
        if self.current_language != language:
            self.current_language = language
            self.settings.setValue('language', language)
            self.update_language()
            global_chatbot.set_default_language(language)
    
    def update_language(self):
        """Update all UI text based on current language"""
        if self.current_language == 'en':
            self.setWindowTitle("🏥 BoCare AI Assistant - Intelligent Medical Assistant")
            self.title_label.setText("BoCare AI Assistant")
            self.subtitle_label.setText("Intelligent medical assistant with conversational AI and automatic triage")
            self.new_session_btn.setText("🔄 New Consultation")
            self.input_label.setText("💬 Describe your symptoms or ask your medical question:")
            self.input_box.setPlaceholderText("Ex: I have a headache for 2 days with fever...")
            self.send_button.setText("📤 Send")
        else:
            self.setWindowTitle("🏥 BoCare AI Assistant - Assistant Médical Intelligent")
            self.title_label.setText("BoCare AI Assistant")
            self.subtitle_label.setText("Assistant médical intelligent avec IA conversationnelle et triage automatique")
            self.new_session_btn.setText("🔄 Nouvelle Consultation")
            self.input_label.setText("💬 Décrivez vos symptômes ou posez votre question médicale :")
            self.input_box.setPlaceholderText("Ex: J'ai mal à la tête depuis 2 jours avec de la fièvre...")
            self.send_button.setText("📤 Envoyer")
    
    def show_about(self):
        """Show about dialog"""
        about_text = """
        <h3>BoCare AI Assistant</h3>
        <p><b>Version:</b> 2.0 Enhanced</p>
        <p><b>Developer:</b> Bocar Thierno Ousmane Ba</p>
        <p><b>Features:</b></p>
        <ul>
        <li>Intelligent medical triage system</li>
        <li>RAG-enhanced responses</li>
        <li>Multi-language support</li>
        <li>Advanced security measures</li>
        </ul>
        <p><b>Disclaimer:</b> This is an AI assistant for preliminary medical guidance only. 
        Always consult healthcare professionals for medical advice.</p>
        """ if self.current_language == 'en' else """
        <h3>BoCare AI Assistant</h3>
        <p><b>Version:</b> 2.0 Amélioré</p>
        <p><b>Développeur:</b> Bocar Thierno Ousmane Ba</p>
        <p><b>Fonctionnalités:</b></p>
        <ul>
        <li>Système de triage médical intelligent</li>
        <li>Réponses améliorées par RAG</li>
        <li>Support multilingue</li>
        <li>Mesures de sécurité avancées</li>
        </ul>
        <p><b>Avertissement:</b> Ceci est un assistant IA pour orientation médicale préliminaire seulement. 
        Consultez toujours des professionnels de santé pour des conseils médicaux.</p>
        """
        
        QMessageBox.about(self, "About BoCare" if self.current_language == 'en' else "À propos de BoCare", about_text)
    
    def export_session(self):
        """Export current session to file"""
        if not self.current_session_id:
            QMessageBox.information(self, "Info", "No active session to export" if self.current_language == 'en' else "Aucune session active à exporter")
            return
        
        session_data = global_chatbot.get_session_summary(self.current_session_id)
        if session_data:
            filename = f"bocare_session_{self.current_session_id[:8]}.json"
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, indent=2, ensure_ascii=False, default=str)
                QMessageBox.information(self, "Success" if self.current_language == 'en' else "Succès", 
                                      f"Session exported to {filename}" if self.current_language == 'en' else f"Session exportée vers {filename}")
            except Exception as e:
                QMessageBox.warning(self, "Error" if self.current_language == 'en' else "Erreur", 
                                  f"Failed to export session: {str(e)}" if self.current_language == 'en' else f"Échec de l'export: {str(e)}")

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.send_message()
        else:
            super().keyPressEvent(event)
