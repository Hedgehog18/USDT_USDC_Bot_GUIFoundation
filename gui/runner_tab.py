from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from storage.database_manager import DatabaseManager


class RunnerTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton("Refresh Runner")
        self.refresh_button.clicked.connect(self.refresh)

        self.auto_refresh_checkbox = QCheckBox("Auto Refresh")
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.auto_refresh_checkbox)
        actions.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(actions)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        lines = [
            "=== System ===",
            f"Mode: {getattr(self.config, 'mode', 'N/A')}",
            f"Symbol: {getattr(self.config, 'symbol', 'N/A')}",
            f"Current Time: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "=== Database Counters ===",
            f"Cycles: {self._safe_count('cycles')}",
            f"Signals: {self._safe_count('trade_signals')}",
            f"Backtest Runs: {self._safe_count('backtest_runs')}",
            f"Paper Runs: {self._safe_count('paper_runs')}",
            f"Paper Safety Events: {self._safe_count('paper_safety_events')}",
            f"System Events: {self._safe_count('system_events')}",
            "",
        ]

        self._append_latest_signal(lines)
        lines.append("")
        self._append_latest_cycle(lines)
        lines.append("")
        self._append_latest_system_event(lines)

        self.output.setPlainText("\n".join(lines))

    def toggle_auto_refresh(self) -> None:
        if self.auto_refresh_checkbox.isChecked():
            self.timer.start()
        else:
            self.timer.stop()

    def _safe_count(self, table_name: str) -> int:
        try:
            return self.database.count_rows(table_name)
        except Exception:
            return 0

    def _append_latest_signal(self, lines: list[str]) -> None:
        lines.append("=== Latest Signal ===")
        try:
            row = self.database.load_latest_signal()
        except Exception as exc:
            lines.append(f"Could not load latest signal: {exc}")
            return

        if not row:
            lines.append("No signals yet.")
            return

        timestamp, decision, confidence, reason = row
        lines.extend([
            f"Timestamp: {timestamp}",
            f"Decision: {decision}",
            f"Confidence: {confidence}",
            f"Reason: {reason}",
        ])

    def _append_latest_cycle(self, lines: list[str]) -> None:
        lines.append("=== Latest Cycle ===")
        try:
            row = self.database.load_latest_cycle()
        except Exception as exc:
            lines.append(f"Could not load latest cycle: {exc}")
            return

        if not row:
            lines.append("No cycles yet.")
            return

        cycle_id, direction, status, open_price, close_price, pnl = row
        lines.extend([
            f"Cycle ID: {cycle_id}",
            f"Direction: {direction}",
            f"Status: {status}",
            f"Open Price: {open_price:.8f}",
            f"Close Price: {close_price:.8f}",
            f"PnL: {self._format_optional_float(pnl)}",
        ])

    def _append_latest_system_event(self, lines: list[str]) -> None:
        lines.append("=== Latest System Event ===")
        try:
            row = self.database.load_latest_system_event()
        except Exception as exc:
            lines.append(f"Could not load latest system event: {exc}")
            return

        if not row:
            lines.append("No system events yet.")
            return

        timestamp, level, module, message = row
        lines.extend([
            f"Timestamp: {timestamp}",
            f"Level: {level}",
            f"Module: {module}",
            f"Message: {message}",
        ])

    def _format_optional_float(self, value) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.8f}"
