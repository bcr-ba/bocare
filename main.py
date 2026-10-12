import sys
from PyQt6.QtWidgets import QApplication
from ui_main import MedicalChatbotApp

if __name__ == "__main__":  # <-- THIS IS IMPORTANT
    app = QApplication(sys.argv)
    window = MedicalChatbotApp()
    window.show()
    sys.exit(app.exec())  # <-- MUST BE app.exec(), not app.exec_()
