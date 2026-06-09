from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from health.health_check import HealthCheck
from storage.database_manager import DatabaseManager


class HealthTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.run_button = QPushButton("Запустити Health Check")
        self.run_button.clicked.connect(self.run_health_check)

        layout = QVBoxLayout()
        layout.addWidget(self.run_button)
        layout.addWidget(self.output)
        self.setLayout(layout)

    def run_health_check(self) -> None:
        report = HealthCheck(config=self.config, database=self.database).run()

        lines = ["=== Health Check ==="]
        for item in report.items:
            status = "OK" if item.ok else "FAIL"
            lines.append(f"[{status}] {item.name}: {item.message}")

        lines.append("")
        lines.append("Система готова до Demo-запуску." if report.ok else "Є проблеми перед запуском.")
        self.output.setPlainText("\n".join(lines))
