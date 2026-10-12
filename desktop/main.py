import logging
import sys

from PyQt6.QtWidgets import QApplication

from desktop import config_loader
from desktop.api_client import BocareApiClient
from desktop.ui_main import MedicalChatbotApp


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    window = MedicalChatbotApp(BocareApiClient(config_loader.settings().api_url))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
