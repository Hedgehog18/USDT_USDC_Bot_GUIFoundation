from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.version import VERSION
from storage.database_manager import DatabaseManager


class DashboardTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton("Refresh Dashboard")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"USDT/USDC Bot MVP - v{VERSION}"))
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        lines = [
            "=== System ===",
            f"Version: {VERSION}",
            "Config: OK",
            "Database: OK",
            f"Mode: {self.config.mode}",
            f"Symbol: {self.config.symbol}",
            f"Database path: {self.config.database_path}",
            "",
            "=== Database Summary ===",
            f"Cycles: {self._safe_count('cycles')}",
            f"Signals: {self._safe_count('trade_signals')}",
            f"Backtest runs: {self._safe_count('backtest_runs')}",
            f"Paper cycles: {self._safe_count('paper_cycles')}",
            f"Paper runs: {self._safe_count('paper_runs')}",
            f"Paper safety events: {self._safe_count('paper_safety_events')}",
            f"Notifications: {self._safe_count('notifications')}",
            "",
        ]

        self._append_latest_backtest(lines)
        lines.append("")
        self._append_latest_paper_run(lines)
        lines.append("")
        self._append_latest_safety_events(lines)
        lines.append("")
        self._append_latest_notifications(lines)
        lines.extend([
            "",
            "=== Suggested next step ===",
            "Run Backtest or Paper Simulation from the corresponding tab.",
        ])

        self.output.setPlainText("\n".join(lines))

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

    def _append_latest_backtest(self, lines: list[str]) -> None:
        lines.append("=== Latest Backtest ===")
        rows = self._load_latest_backtest()
        if not rows:
            lines.append("No backtest runs yet.")
            return

        run_id, timestamp, symbol, interval, candles, trades, win_rate, net_profit, roi, max_drawdown = rows[0]
        lines.extend([
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
        ])

    def _append_latest_paper_run(self, lines: list[str]) -> None:
        lines.append("=== Latest Paper Run ===")
        rows = self._load_latest_paper_run()
        if not rows:
            lines.append("No paper runs yet.")
            return

        run_id, timestamp, iterations, opened, closed, stops, usdt, usdc, value, rating, summary = rows[0]
        lines.extend([
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
        ])

    def _append_latest_safety_events(self, lines: list[str]) -> None:
        lines.append("=== Latest Paper Safety Events ===")
        rows = self._load_latest_safety_events()
        if not rows:
            lines.append("No safety events yet.")
            return

        for timestamp, level, allowed, reason, value in rows:
            status = "ALLOWED" if allowed else "BLOCKED"
            lines.append(f"{timestamp} | {level} | {status} | value={value:.8f} | {reason}")

    def _append_latest_notifications(self, lines: list[str]) -> None:
        lines.append("=== Latest Notifications ===")
        rows = self._load_latest_notifications()
        if not rows:
            lines.append("No notifications yet.")
            return

        for item in rows:
            read_state = "READ" if item.is_read else "UNREAD"
            level = getattr(item.level, "value", item.level)
            lines.append(
                f"{item.created_at.isoformat()} | {level} | {read_state} | "
                f"{item.title}: {item.message}"
            )
