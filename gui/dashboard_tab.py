from PySide6.QtWidgets import (
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.version import VERSION
from storage.database_manager import DatabaseManager


class DashboardTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.system_output = self._create_readonly_text(minimum_height=135)
        self.database_output = self._create_readonly_text(minimum_height=160)
        self.backtest_output = self._create_readonly_text(minimum_height=165)
        self.paper_output = self._create_readonly_text(minimum_height=190)
        self.safety_output = self._create_readonly_text(minimum_height=150)
        self.notifications_output = self._create_readonly_text(minimum_height=150)
        self.next_step_output = self._create_readonly_text(minimum_height=80)

        self.refresh_button = QPushButton("Refresh Dashboard")
        self.refresh_button.clicked.connect(self.refresh)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"USDT/USDC Bot MVP - v{VERSION}"))
        header.addStretch()
        header.addWidget(self.refresh_button)

        content = QWidget()
        content_layout = QGridLayout()
        content_layout.addWidget(self._section("System", self.system_output), 0, 0)
        content_layout.addWidget(self._section("Database Summary", self.database_output), 0, 1)
        content_layout.addWidget(self._section("Latest Backtest", self.backtest_output), 1, 0)
        content_layout.addWidget(self._section("Latest Paper Run", self.paper_output), 1, 1)
        content_layout.addWidget(self._section("Safety Events", self.safety_output), 2, 0)
        content_layout.addWidget(self._section("Notifications", self.notifications_output), 2, 1)
        content_layout.addWidget(self._section("Suggested Next Step", self.next_step_output), 3, 0, 1, 2)
        content_layout.setColumnStretch(0, 1)
        content_layout.setColumnStretch(1, 1)
        content.setLayout(content_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content)

        layout = QVBoxLayout()
        layout.addLayout(header)
        layout.addWidget(scroll_area)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        system_lines = [
            f"Version: {VERSION}",
            "Config: OK",
            "Database: OK",
            f"Mode: {self.config.mode}",
            f"Symbol: {self.config.symbol}",
            f"Database path: {self.config.database_path}",
        ]
        database_lines = [
            f"Cycles: {self._safe_count('cycles')}",
            f"Signals: {self._safe_count('trade_signals')}",
            f"Backtest runs: {self._safe_count('backtest_runs')}",
            f"Paper cycles: {self._safe_count('paper_cycles')}",
            f"Paper runs: {self._safe_count('paper_runs')}",
            f"Paper safety events: {self._safe_count('paper_safety_events')}",
            f"Notifications: {self._safe_count('notifications')}",
        ]

        backtest_lines = self._latest_backtest_lines()
        paper_lines = self._latest_paper_run_lines()
        safety_lines = self._latest_safety_event_lines()
        notification_lines = self._latest_notification_lines()
        next_step_lines = ["Run Backtest or Paper Simulation from the corresponding tab."]

        self.system_output.setPlainText("\n".join(system_lines))
        self.database_output.setPlainText("\n".join(database_lines))
        self.backtest_output.setPlainText("\n".join(backtest_lines))
        self.paper_output.setPlainText("\n".join(paper_lines))
        self.safety_output.setPlainText("\n".join(safety_lines))
        self.notifications_output.setPlainText("\n".join(notification_lines))
        self.next_step_output.setPlainText("\n".join(next_step_lines))

        compatibility_lines = [
            "=== System ===",
            *system_lines,
            "",
            "=== Database Summary ===",
            *database_lines,
            "",
            "=== Latest Backtest ===",
            *backtest_lines,
            "",
            "=== Latest Paper Run ===",
            *paper_lines,
            "",
            "=== Latest Paper Safety Events ===",
            *safety_lines,
            "",
            "=== Latest Notifications ===",
            *notification_lines,
            "",
            "=== Suggested next step ===",
            *next_step_lines,
        ]
        self.output.setPlainText("\n".join(compatibility_lines))

    @staticmethod
    def _create_readonly_text(minimum_height: int) -> QTextEdit:
        widget = QTextEdit()
        widget.setReadOnly(True)
        widget.setMinimumHeight(minimum_height)
        return widget

    @staticmethod
    def _section(title: str, widget: QWidget) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout()
        layout.addWidget(widget)
        group.setLayout(layout)
        return group

    def _safe_count(self, table_name: str) -> int:
        try:
            return self.database.count_rows(table_name)
        except Exception:
            return 0

    def _load_latest_backtest(self) -> list:
        try:
            return self.database.load_recent_backtest_runs(limit=1)
        except Exception:
            return []

    def _load_latest_paper_run(self) -> list:
        try:
            return self.database.load_recent_paper_runs(limit=1)
        except Exception:
            return []

    def _load_latest_safety_events(self) -> list:
        try:
            return self.database.load_recent_paper_safety_events(limit=5)
        except Exception:
            return []

    def _load_latest_notifications(self) -> list:
        try:
            return self.database.load_recent_notifications(limit=5)
        except Exception:
            return []

    def _latest_backtest_lines(self) -> list[str]:
        rows = self._load_latest_backtest()
        if not rows:
            return ["No backtest runs yet."]

        run_id, timestamp, symbol, interval, candles, trades, win_rate, net_profit, roi, max_drawdown = rows[0]
        return [
            f"Run ID: {run_id}",
            f"Timestamp: {timestamp}",
            f"Symbol: {symbol}",
            f"Interval: {interval}",
            f"Candles: {candles}",
            f"Trades: {trades}",
            f"Win rate: {win_rate * 100:.2f}%",
            f"Net profit: {net_profit:.8f}",
            f"ROI: {roi * 100:.4f}%",
            f"Max drawdown: {max_drawdown * 100:.4f}%",
        ]

    def _latest_paper_run_lines(self) -> list[str]:
        rows = self._load_latest_paper_run()
        if not rows:
            return ["No paper runs yet."]

        run_id, timestamp, iterations, opened, closed, stops, usdt, usdc, value, rating, summary = rows[0]
        return [
            f"Run ID: {run_id}",
            f"Timestamp: {timestamp}",
            f"Iterations: {iterations}",
            f"Opened cycles: {opened}",
            f"Closed cycles: {closed}",
            f"Safety stops: {stops}",
            f"Final USDT: {usdt:.8f}",
            f"Final USDC: {usdc:.8f}",
            f"Final value: {value:.8f}",
            f"Rating: {rating}",
            f"Summary: {summary}",
        ]

    def _latest_safety_event_lines(self) -> list[str]:
        rows = self._load_latest_safety_events()
        if not rows:
            return ["No safety events yet."]

        lines = []
        for timestamp, level, allowed, reason, value in rows:
            status = "ALLOWED" if allowed else "BLOCKED"
            lines.append(f"{timestamp} | {level} | {status} | value={value:.8f} | {reason}")
        return lines

    def _latest_notification_lines(self) -> list[str]:
        rows = self._load_latest_notifications()
        if not rows:
            return ["No notifications yet."]

        lines = []
        for item in rows:
            read_state = "READ" if item.is_read else "UNREAD"
            level = getattr(item.level, "value", item.level)
            lines.append(
                f"{item.created_at.isoformat()} | {level} | {read_state} | "
                f"{item.title}: {item.message}"
            )
        return lines
