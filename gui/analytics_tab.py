from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget

from storage.database_manager import DatabaseManager


def calculate_drawdown_curve(values: list[float]) -> list[float]:
    drawdowns: list[float] = []
    peak = None
    for value in values:
        peak = value if peak is None else max(peak, value)
        drawdowns.append(((value - peak) / peak) if peak else 0.0)
    return drawdowns


class AnalyticsTab(QWidget):
    def __init__(self, database: DatabaseManager) -> None:
        super().__init__()
        self.database = database

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(125)

        self.equity_figure = Figure(figsize=(8, 3.6), constrained_layout=True)
        self.equity_canvas = FigureCanvas(self.equity_figure)

        self.drawdown_figure = Figure(figsize=(8, 3.6), constrained_layout=True)
        self.drawdown_canvas = FigureCanvas(self.drawdown_figure)

        self.pnl_figure = Figure(figsize=(8, 3.6), constrained_layout=True)
        self.pnl_canvas = FigureCanvas(self.pnl_figure)
        for canvas in (self.equity_canvas, self.drawdown_canvas, self.pnl_canvas):
            canvas.setMinimumHeight(330)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.refresh_button = QPushButton("Refresh Analytics")
        self.refresh_button.clicked.connect(self.refresh)

        content = QWidget()
        content_layout = QVBoxLayout()
        content_layout.addWidget(QLabel("Summary:"))
        content_layout.addWidget(self.summary)
        content_layout.addWidget(QLabel("Equity Curve:"))
        content_layout.addWidget(self.equity_canvas)
        content_layout.addWidget(QLabel("Drawdown Curve:"))
        content_layout.addWidget(self.drawdown_canvas)
        content_layout.addWidget(QLabel("Trade PnL Distribution:"))
        content_layout.addWidget(self.pnl_canvas)
        content_layout.addStretch()
        content.setLayout(content_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(content)

        layout = QVBoxLayout()
        layout.addWidget(self.refresh_button)
        layout.addWidget(scroll_area)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        run = self._load_latest_backtest_run()
        if run is None:
            self.summary.setPlainText("No backtest runs yet.")
            self._draw_empty_charts("No backtest runs yet.")
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
            self._draw_empty_chart(self.equity_figure, self.equity_canvas, "No data available.")
            self._draw_empty_chart(self.drawdown_figure, self.drawdown_canvas, "No data available.")
        else:
            indexes = [point[0] for point in points]
            values = [point[1] for point in points]
            self._draw_equity_curve(indexes, values, run_id)
            self._draw_drawdown_curve(indexes, calculate_drawdown_curve(values), run_id)

        trades = self._load_trades(run_id)
        if not trades:
            self.summary.append("\nNo trades for latest backtest.")
            self._draw_empty_chart(self.pnl_figure, self.pnl_canvas, "No data available.")
            return

        net_profits = [trade[7] for trade in trades]
        self._draw_trade_pnl_distribution(net_profits, run_id)

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

    def _load_trades(self, run_id: int) -> list[tuple]:
        try:
            return self.database.load_backtest_trades(run_id)
        except Exception:
            return []

    def _draw_equity_curve(self, indexes: list[int], values: list[float], run_id: int) -> None:
        self.equity_figure.clear()
        axes = self.equity_figure.add_subplot(111)
        axes.plot(indexes, values, color="#2563eb", linewidth=1.8)
        axes.set_title(f"Backtest #{run_id} Equity Curve")
        axes.set_xlabel("Point")
        axes.set_ylabel("Portfolio value")
        axes.grid(True, alpha=0.3)
        self.equity_canvas.draw()

    def _draw_drawdown_curve(self, indexes: list[int], drawdowns: list[float], run_id: int) -> None:
        self.drawdown_figure.clear()
        axes = self.drawdown_figure.add_subplot(111)
        axes.plot(indexes, [value * 100 for value in drawdowns], color="#dc2626", linewidth=1.8)
        axes.fill_between(indexes, [value * 100 for value in drawdowns], 0, color="#fecaca", alpha=0.45)
        axes.set_title(f"Backtest #{run_id} Drawdown Curve")
        axes.set_xlabel("Point")
        axes.set_ylabel("Drawdown (%)")
        axes.grid(True, alpha=0.3)
        self.drawdown_canvas.draw()

    def _draw_trade_pnl_distribution(self, net_profits: list[float], run_id: int) -> None:
        self.pnl_figure.clear()
        axes = self.pnl_figure.add_subplot(111)
        colors = ["#16a34a" if value >= 0 else "#dc2626" for value in net_profits]
        axes.hist(net_profits, bins=min(20, max(1, len(net_profits))), color="#64748b", alpha=0.75)
        axes.scatter(net_profits, [0 for _ in net_profits], c=colors, s=28, alpha=0.85)
        axes.axvline(0, color="#111827", linewidth=1.0)
        axes.set_title(f"Backtest #{run_id} Trade PnL Distribution")
        axes.set_xlabel("Net profit")
        axes.set_ylabel("Trades")
        axes.grid(True, alpha=0.3)
        self.pnl_canvas.draw()

    def _draw_empty_charts(self, message: str) -> None:
        self._draw_empty_chart(self.equity_figure, self.equity_canvas, message)
        self._draw_empty_chart(self.drawdown_figure, self.drawdown_canvas, message)
        self._draw_empty_chart(self.pnl_figure, self.pnl_canvas, message)

    @staticmethod
    def _draw_empty_chart(figure: Figure, canvas: FigureCanvas, message: str) -> None:
        figure.clear()
        axes = figure.add_subplot(111)
        axes.text(0.5, 0.5, message, ha="center", va="center", transform=axes.transAxes)
        axes.set_axis_off()
        canvas.draw()
