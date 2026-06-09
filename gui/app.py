import sys

from PySide6.QtWidgets import QApplication

from app.app_logger import AppLogger
from config.config_manager import ConfigManager
from gui.main_window import MainWindow


def main() -> None:
    config = ConfigManager().config
    AppLogger(config).configure()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
