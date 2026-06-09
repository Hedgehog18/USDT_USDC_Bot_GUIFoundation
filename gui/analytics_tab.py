from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from storage.database_manager import DatabaseManager


class AnalyticsTab(QWidget):
    def __init__(self, database: DatabaseManager) -> None:
        super().__init__()
        self.database = database

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)

        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvas(self.figure)

        self.refresh_button = QPushButton("Refresh Analytics")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout()
        layout.addWidget(self.refresh_button)
        layout.addWidget(QLabel("Summary:"))
        layout.addWidget(self.summary)
        layout.addWidget(QLabel("Equity curve:"))
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        run = self._load_latest_backtest_run()
        if run is None:
            self.summary.setPlainText("No backtest runs yet.")
            self._draw_empty_chart("No backtest runs yet.")
            return

        run_id, timestamp, symbol, interval, candles, trades, win_rate, net_profit, roi, max_drawdown = run
        self.summary.setPlainText(
            "\n".join([
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
        )

        points = self._load_equity_points(run_id)
        if not points:
            self.summary.append("\nNo equity points for latest backtest.")
            self._draw_empty_chart("No equity points for latest backtest.")
            return

        indexes = [point[0] for point in points]
        values = [point[1] for point in points]
        self._draw_equity_curve(indexes, values, run_id)

    def _load_latest_backtest_run(self):
        try:
            return self.database.load_latest_backtest_run()
        except AttributeError:
            rows = self.database.load_recent_backtest_runs(limit=1)
            return rows[0] if rows else None
        except Exception:
            return None

    def _load_equity_points(self, run_id: int) -> list[tuple]:
        try:
            return self.database.load_backtest_equity_points(run_id)
        except Exception:
            return []

    def _draw_equity_curve(self, indexes: list[int], values: list[float], run_id: int) -> None:
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.plot(indexes, values, color="#2563eb", linewidth=1.8)
        axes.set_title(f"Backtest #{run_id} Equity Curve")
        axes.set_xlabel("Point")
        axes.set_ylabel("Portfolio value")
        axes.grid(True, alpha=0.3)
        self.figure.tight_layout()
        self.canvas.draw()

    def _draw_empty_chart(self, message: str) -> None:
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.text(0.5, 0.5, message, ha="center", va="center", transform=axes.transAxes)
        axes.set_axis_off()
        self.figure.tight_layout()
        self.canvas.draw()
