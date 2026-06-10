from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from analytics.decision_diagnostics_engine import DecisionDiagnosticsEngine
from analytics.entry_zone_diagnostics_engine import EntryZoneDiagnosticsEngine
from analytics.filter_pass_diagnostics_engine import FilterPassDiagnosticsEngine
from analytics.order_book_diagnostics_engine import OrderBookDiagnosticsEngine
from analytics.risk_diagnostics_engine import RiskDiagnosticsEngine
from analytics.strategy_tuning_report_engine import StrategyTuningReportEngine
from analytics.strategy_validation_engine import StrategyValidationEngine
from analytics.validation_summary_engine import ValidationSummaryEngine
from config.config_manager import ConfigManager
from storage.database_manager import DatabaseManager


def calculate_drawdown_curve(values: list[float]) -> list[float]:
    drawdowns: list[float] = []
    peak = None
    for value in values:
        peak = value if peak is None else max(peak, value)
        drawdowns.append(((value - peak) / peak) if peak else 0.0)
    return drawdowns


class AnalyticsTab(QWidget):
    def __init__(self, database: DatabaseManager, config=None) -> None:
        super().__init__()
        self.database = database
        self.config = config or ConfigManager().config

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(150)

        self.insights = QTextEdit()
        self.insights.setReadOnly(True)
        self.insights.setMinimumHeight(150)

        self.strategy_summary = QTextEdit()
        self.strategy_summary.setReadOnly(True)
        self.strategy_summary.setMinimumHeight(150)

        self.strategy_tuning = QTextEdit()
        self.strategy_tuning.setReadOnly(True)
        self.strategy_tuning.setMinimumHeight(165)

        self.entry_zone_diagnostics = QTextEdit()
        self.entry_zone_diagnostics.setReadOnly(True)
        self.entry_zone_diagnostics.setMinimumHeight(165)

        self.filter_pass_diagnostics = QTextEdit()
        self.filter_pass_diagnostics.setReadOnly(True)
        self.filter_pass_diagnostics.setMinimumHeight(175)

        self.order_book_diagnostics = QTextEdit()
        self.order_book_diagnostics.setReadOnly(True)
        self.order_book_diagnostics.setMinimumHeight(175)

        self.validation_summary = QTextEdit()
        self.validation_summary.setReadOnly(True)
        self.validation_summary.setMinimumHeight(150)

        self.decision_diagnostics = QTextEdit()
        self.decision_diagnostics.setReadOnly(True)
        self.decision_diagnostics.setMinimumHeight(150)

        self.risk_diagnostics = QTextEdit()
        self.risk_diagnostics.setReadOnly(True)
        self.risk_diagnostics.setMinimumHeight(150)

        self.equity_figure = Figure(figsize=(8, 3.6), constrained_layout=True)
        self.equity_canvas = FigureCanvas(self.equity_figure)

        self.drawdown_figure = Figure(figsize=(8, 3.6), constrained_layout=True)
        self.drawdown_canvas = FigureCanvas(self.drawdown_figure)

        self.pnl_figure = Figure(figsize=(8, 3.6), constrained_layout=True)
        self.pnl_canvas = FigureCanvas(self.pnl_figure)
        for canvas in (self.equity_canvas, self.drawdown_canvas, self.pnl_canvas):
            canvas.setMinimumHeight(380)
            canvas.setMinimumWidth(1100)
            canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.refresh_button = QPushButton("Refresh Analytics")
        self.refresh_button.clicked.connect(self.refresh)

        top_panel = QWidget()
        top_layout = QGridLayout()
        top_layout.addWidget(self._section("Validation Summary", self.validation_summary), 0, 0)
        top_layout.addWidget(self._section("Latest Backtest Insights", self.insights), 0, 1)
        top_layout.addWidget(self._section("Summary", self.summary), 1, 0)
        top_layout.addWidget(self._section("Strategy Summary", self.strategy_summary), 1, 1)
        top_layout.addWidget(self._section("Risk Diagnostics", self.risk_diagnostics), 2, 0)
        top_layout.addWidget(self._section("Decision Diagnostics", self.decision_diagnostics), 2, 1)
        top_layout.addWidget(self._section("Strategy Tuning Report", self.strategy_tuning), 3, 0)
        top_layout.addWidget(
            self._section("Entry Zone Diagnostics", self.entry_zone_diagnostics),
            3,
            1,
        )
        top_layout.addWidget(
            self._section("Filter Pass Diagnostics", self.filter_pass_diagnostics),
            4,
            0,
        )
        top_layout.addWidget(
            self._section("Order Book Diagnostics", self.order_book_diagnostics),
            4,
            1,
        )
        top_layout.setColumnStretch(0, 1)
        top_layout.setColumnStretch(1, 1)
        top_panel.setLayout(top_layout)

        top_scroll_area = QScrollArea()
        top_scroll_area.setWidgetResizable(True)
        top_scroll_area.setWidget(top_panel)

        charts_content = QWidget()
        charts_layout = QVBoxLayout()
        charts_layout.addWidget(QLabel("Equity Curve:"))
        charts_layout.addWidget(self.equity_canvas)
        charts_layout.addWidget(QLabel("Drawdown Curve:"))
        charts_layout.addWidget(self.drawdown_canvas)
        charts_layout.addWidget(QLabel("Trade PnL Distribution:"))
        charts_layout.addWidget(self.pnl_canvas)
        charts_layout.addStretch()
        charts_content.setLayout(charts_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(charts_content)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setObjectName("analytics_main_splitter")
        self.main_splitter.addWidget(top_scroll_area)
        self.main_splitter.addWidget(scroll_area)
        self.main_splitter.setSizes([430, 720])

        layout = QVBoxLayout()
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.main_splitter)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self.validation_summary.setPlainText("\n".join(self._validation_summary_lines()))
        self.strategy_summary.setPlainText("\n".join(self._strategy_summary_lines()))
        self.strategy_tuning.setPlainText("\n".join(self._strategy_tuning_lines()))
        self.entry_zone_diagnostics.setPlainText("\n".join(self._entry_zone_diagnostics_lines()))
        self.filter_pass_diagnostics.setPlainText("\n".join(self._filter_pass_diagnostics_lines()))
        self.order_book_diagnostics.setPlainText("\n".join(self._order_book_diagnostics_lines()))
        self.decision_diagnostics.setPlainText("\n".join(self._decision_diagnostics_lines()))
        self.risk_diagnostics.setPlainText("\n".join(self._risk_diagnostics_lines()))
        run = self._load_latest_backtest_run()
        if run is None:
            self.summary.setPlainText("No backtest runs yet.")
            self.insights.setPlainText("No backtest insights yet.")
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
        self.insights.setPlainText("\n".join(self._load_backtest_insights_lines(run_id)))

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

    def _load_backtest_insights_lines(self, run_id: int) -> list[str]:
        path = Path("reports") / f"backtest_run_{run_id}_insights.txt"
        if not path.exists():
            return ["No insights TXT for latest backtest yet."]

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return [f"Insights TXT: {path}", *lines]

    def _strategy_summary_lines(self) -> list[str]:
        try:
            summary = StrategyValidationEngine(self.database).build_summary()
        except Exception as exc:
            return [f"Could not load strategy summary: {exc}"]

        if summary.total_signals == 0:
            return ["No strategy data available."]

        lines = [
            f"Signals generated: {summary.total_signals}",
            f"Buy signals: {summary.buy_signals}",
            f"Sell signals: {summary.sell_signals}",
            f"Avg confidence: {summary.average_confidence * 100:.2f}%",
            f"Avg spread: {summary.average_spread:.8f}",
            f"Avg volatility: {summary.average_volatility:.8f}",
            "Market regimes:",
        ]
        if summary.market_regime_distribution:
            lines.extend(
                f"- {regime}: {count}"
                for regime, count in summary.market_regime_distribution.items()
            )
        else:
            lines.append("- No market snapshots yet.")
        return lines

    def _validation_summary_lines(self) -> list[str]:
        try:
            summary = ValidationSummaryEngine(self.database).build_summary()
        except Exception as exc:
            return [f"Could not load validation summary: {exc}"]

        lines = [
            f"Overall status: {summary.overall_status}",
            f"Strategy signals: {summary.strategy_signals}",
            f"Latest backtest trades: {summary.latest_backtest_trades}",
            f"Latest backtest net profit: {summary.latest_backtest_net_profit:.8f}",
            f"Paper cycles: {summary.paper_cycles}",
            f"Paper net profit: {summary.paper_net_profit:.8f}",
            f"Risk blocked rate: {summary.risk_blocked_rate * 100:.2f}%",
            "Warnings:",
        ]
        if summary.warnings:
            lines.extend(f"- {item}" for item in summary.warnings)
        else:
            lines.append("- None")
        lines.extend(["Next action:", summary.next_action])
        return lines

    def _strategy_tuning_lines(self) -> list[str]:
        try:
            report = StrategyTuningReportEngine(self.database).build_report(top=3)
        except Exception as exc:
            return [f"Could not load strategy tuning report: {exc}"]

        if report.total_signals == 0:
            return ["No tuning data available."]

        lines = [
            "Simulation only. DecisionEngine, RiskManager, config, and trades are unchanged.",
            f"Total signals: {report.total_signals}",
        ]
        for item in report.thresholds:
            lines.extend([
                "",
                f"min_confidence >= {item.threshold:.1f}",
                f"Total passed: {item.total_passed}",
                f"Pass rate: {item.pass_rate * 100:.2f}%",
                f"BUY candidates: {item.buy_candidates}",
                f"SELL candidates: {item.sell_candidates}",
                f"WAIT still blocked: {item.wait_still_blocked}",
                "Top remaining reasons:",
                *self._reason_lines(item.top_remaining_reasons),
            ])
        return lines

    def _entry_zone_diagnostics_lines(self) -> list[str]:
        try:
            summary = EntryZoneDiagnosticsEngine(self.database).build_summary()
        except Exception as exc:
            return [f"Could not load entry zone diagnostics: {exc}"]

        if summary.total_snapshots == 0:
            return ["No entry zone data available."]

        lines = [
            f"Total snapshots: {summary.total_snapshots}",
            f"BUY zone count (work_position <= 20): {summary.potential_buy_zone_count}",
            f"SELL zone count (work_position >= 80): {summary.potential_sell_zone_count}",
            f"Center zone count (40 <= work_position <= 60): {summary.center_zone_count}",
            f"Avg work_position: {summary.average_work_position:.4f}",
            f"Min work_position: {summary.min_work_position:.4f}",
            f"Max work_position: {summary.max_work_position:.4f}",
            f"Median work_position: {summary.median_work_position:.4f}",
            f"Average spread: {summary.average_spread:.8f}",
            f"Average market health score: {summary.average_market_health_score:.4f}",
            "Position buckets:",
        ]
        lines.extend(f"- {bucket}: {count}" for bucket, count in summary.buckets.items())
        lines.append("Market regimes:")
        if summary.market_regime_distribution:
            lines.extend(
                f"- {regime}: {count}"
                for regime, count in summary.market_regime_distribution.items()
            )
        else:
            lines.append("- No market snapshots yet.")
        return lines

    def _filter_pass_diagnostics_lines(self) -> list[str]:
        try:
            summary = FilterPassDiagnosticsEngine(self.database, self.config).build_summary(latest=5)
        except Exception as exc:
            return [f"Could not load filter pass diagnostics: {exc}"]

        if summary.total_entry_zone_snapshots == 0:
            return ["No filter pass diagnostics data available."]

        lines = []
        if summary.warning:
            lines.append(f"WARNING: {summary.warning}")
            lines.append("")
        lines.extend([
            f"Total entry zone snapshots: {summary.total_entry_zone_snapshots}",
            f"BUY zone snapshots: {summary.buy_zone_snapshots}",
            f"SELL zone snapshots: {summary.sell_zone_snapshots}",
            "Filter pass rates:",
        ])
        lines.extend(
            (
                f"- {item.name}: passed={item.passed} failed={item.failed} "
                f"unknown={item.unknown} pass_rate={item.pass_rate * 100:.2f}%"
            )
            for item in summary.filters
        )
        lines.append("Top blocking filters:")
        if summary.top_blocking_filters:
            lines.extend(f"- {name}: {failed}" for name, failed in summary.top_blocking_filters)
        else:
            lines.append("- No blocking filters detected.")
        lines.append("Latest blocked entry-zone snapshots:")
        if summary.latest_blocked_snapshots:
            lines.extend(
                (
                    f"- {item.timestamp} | {item.zone} | "
                    f"work_position={item.work_position:.4f} | "
                    f"failed={', '.join(item.failed_filters)}"
                )
                for item in summary.latest_blocked_snapshots
            )
        else:
            lines.append("- No blocked entry-zone snapshots.")
        return lines

    def _order_book_diagnostics_lines(self) -> list[str]:
        try:
            summary = OrderBookDiagnosticsEngine(self.database, self.config).build_summary(latest=5)
        except Exception as exc:
            return [f"Could not load order book diagnostics: {exc}"]

        if summary.total_snapshots == 0:
            return ["No order book diagnostics data available."]

        lines = [
            f"Total snapshots: {summary.total_snapshots}",
            f"Entry-zone snapshots: {summary.entry_zone_snapshots}",
            "Pressure distribution:",
        ]
        lines.extend(
            f"- {pressure}: {count}"
            for pressure, count in summary.order_book_pressure_distribution.items()
        )
        lines.append("BUY-zone:")
        lines.extend(
            f"- {pressure}: {count}"
            for pressure, count in summary.buy_zone_distribution.items()
        )
        lines.append("SELL-zone:")
        lines.extend(
            f"- {pressure}: {count}"
            for pressure, count in summary.sell_zone_distribution.items()
        )
        lines.extend([
            f"Avg imbalance: {summary.average_order_book_imbalance:.6f}",
            f"Min imbalance: {summary.min_order_book_imbalance:.6f}",
            f"Max imbalance: {summary.max_order_book_imbalance:.6f}",
            "Latest entry-zone snapshots:",
        ])
        if summary.latest_entry_zone_snapshots:
            lines.extend(
                (
                    f"- {item.timestamp} | {item.direction_candidate} | "
                    f"work={item.work_position:.2f} | pressure={item.order_book_pressure} | "
                    f"imb={item.order_book_imbalance:.4f} | micro={item.micro_trend} | "
                    f"confidence={item.center_confidence}"
                )
                for item in summary.latest_entry_zone_snapshots
            )
        else:
            lines.append("- No entry-zone snapshots.")
        return lines

    def _decision_diagnostics_lines(self) -> list[str]:
        try:
            summary = DecisionDiagnosticsEngine(self.database).build_summary(top=3)
        except Exception as exc:
            return [f"Could not load decision diagnostics: {exc}"]

        if summary.total_decisions == 0:
            return ["No decision diagnostics data available."]

        lines = [
            f"Total decisions/signals: {summary.total_decisions}",
            f"BUY count: {summary.buy_count}",
            f"SELL count: {summary.sell_count}",
            f"WAIT count: {summary.wait_count}",
            f"Risk blocked: {summary.risk_blocked_count}",
            "WAIT reasons:",
            *self._reason_lines(summary.top_wait_reasons),
            "BUY reasons:",
            *self._reason_lines(summary.top_buy_reasons),
            "SELL reasons:",
            *self._reason_lines(summary.top_sell_reasons),
            "Confidence distribution:",
        ]
        if summary.confidence_distribution:
            lines.extend(
                f"- {confidence}: {count}"
                for confidence, count in summary.confidence_distribution.items()
            )
        else:
            lines.append("- No confidence data.")
        return lines

    def _risk_diagnostics_lines(self) -> list[str]:
        try:
            summary = RiskDiagnosticsEngine(self.database).build_summary(top=3, latest=5)
        except Exception as exc:
            return [f"Could not load risk diagnostics: {exc}"]

        if summary.total_audited_decisions == 0:
            return ["No risk diagnostics data available."]

        lines = [
            f"Total audited decisions: {summary.total_audited_decisions}",
            f"Allowed count: {summary.allowed_count}",
            f"Blocked count: {summary.blocked_count}",
            f"Blocked rate: {summary.blocked_rate * 100:.2f}%",
            "Top risk reasons:",
            *self._reason_lines(summary.top_risk_reasons),
            "Blocked action distribution:",
        ]
        if summary.blocked_action_distribution:
            lines.extend(
                f"- {action}: {count}"
                for action, count in summary.blocked_action_distribution.items()
            )
        else:
            lines.append("- No blocked decisions.")

        lines.append("Latest blocked decisions:")
        if summary.latest_blocked_decisions:
            lines.extend(
                f"- {item.timestamp} | {item.decision} | {item.risk_reason} | {item.reason}"
                for item in summary.latest_blocked_decisions
            )
        else:
            lines.append("- No blocked decisions.")
        return lines

    @staticmethod
    def _reason_lines(rows: list[tuple[str, int]]) -> list[str]:
        if not rows:
            return ["- No data."]
        return [f"- {reason}: {count}" for reason, count in rows]

    @staticmethod
    def _section(title: str, widget: QWidget) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout()
        layout.addWidget(widget)
        group.setLayout(layout)
        return group

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
