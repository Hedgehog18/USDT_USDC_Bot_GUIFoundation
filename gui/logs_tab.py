from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from storage.database_manager import DatabaseManager


class LogsTab(QWidget):
    def __init__(self, log_file_path: str, database: DatabaseManager) -> None:
        super().__init__()
        self.log_file_path = log_file_path
        self.database = database

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["ALL", "INFO", "WARNING", "ERROR", "CRITICAL"])

        self.source_combo = QComboBox()
        self.source_combo.addItems(["Both", "File log", "System events"])

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)

        self.clear_button = QPushButton("Clear View")
        self.clear_button.clicked.connect(self.output.clear)

        self.auto_refresh_checkbox = QCheckBox("Auto Refresh")
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Level:"))
        filters.addWidget(self.level_combo)
        filters.addWidget(QLabel("Source:"))
        filters.addWidget(self.source_combo)
        filters.addStretch()

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.auto_refresh_checkbox)
        actions.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(filters)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        source = self.source_combo.currentText()
        level = self.level_combo.currentText()
        lines: list[str] = []

        if source in {"Both", "File log"}:
            lines.append("=== File log ===")
            lines.extend(self._read_file_log_lines(level))
            lines.append("")

        if source in {"Both", "System events"}:
            lines.append("=== System events ===")
            lines.extend(self._read_system_event_lines(level))

        self.output.setPlainText("\n".join(lines).rstrip())

    def toggle_auto_refresh(self) -> None:
        if self.auto_refresh_checkbox.isChecked():
            self.timer.start()
        else:
            self.timer.stop()

    def _read_file_log_lines(self, level: str) -> list[str]:
        path = Path(self.log_file_path)
        if not path.exists():
            return ["Log file does not exist yet."]

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        filtered = [
            line for line in lines[-500:]
            if self._passes_level_filter(line, level)
        ]
        return filtered[-500:] if filtered else ["No file log entries match the selected filter."]

    def _read_system_event_lines(self, level: str) -> list[str]:
        try:
            rows = self.database.load_recent_system_events(limit=200)
        except Exception as exc:
            return [f"Could not load system events: {exc}"]

        filtered = [
            row for row in rows
            if level == "ALL" or row[1] == level
        ]
        if not filtered:
            return ["No system events yet."]

        return [
            f"{timestamp} | {event_level} | {module} | {message}"
            for timestamp, event_level, module, message in filtered
        ]

    def _passes_level_filter(self, line: str, level: str) -> bool:
        if level == "ALL":
            return True
        if f"| {level} |" in line:
            return True
        return level in line
