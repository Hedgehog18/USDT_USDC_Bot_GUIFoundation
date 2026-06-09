import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backtest.backtest_engine import BacktestEngine
from backtest.backtest_insights_engine import BacktestInsightsEngine
from backtest.backtest_insights_exporter import BacktestInsightsExporter
from backtest.backtest_report_exporter import BacktestReportExporter
from backtest.equity_analytics_engine import EquityAnalyticsEngine
from backtest.historical_data_provider import HistoricalDataProvider
from config.config_manager import ConfigManager
from health.health_check import HealthCheck
from market.binance_market_data_provider import BinanceMarketDataProvider
from paper.paper_trading_engine import PaperTradingEngine
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
        layout.addWidget(QLabel("USDT/USDC Bot MVP"))
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        lines = [
            "=== System ===",
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


class BacktestTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.logger = logging.getLogger("usdt_usdc_bot")

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.interval_input = QLineEdit(self.config.backtest_interval or "1m")
        self.interval_input.setPlaceholderText("Interval")

        self.limit_input = QLineEdit(str(self.config.backtest_limit or 500))
        self.limit_input.setPlaceholderText("Limit")

        self.start_button = QPushButton("Start Backtest")
        self.start_button.clicked.connect(self.run_backtest)

        self.refresh_button = QPushButton("Показати останні Backtest Runs")
        self.refresh_button.clicked.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Interval:"))
        controls.addWidget(self.interval_input)
        controls.addWidget(QLabel("Limit:"))
        controls.addWidget(self.limit_input)
        controls.addWidget(self.start_button)
        controls.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.refresh_button)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self.output.setPlainText("\n".join(self._build_summary_lines()))

    def run_backtest(self) -> None:
        interval = self.interval_input.text().strip()
        raw_limit = self.limit_input.text().strip()

        if not interval:
            self.output.setPlainText("Interval не може бути порожнім.")
            return

        try:
            limit = int(raw_limit)
        except ValueError:
            self.output.setPlainText("Limit має бути цілим числом більше 0.")
            return

        if limit <= 0:
            self.output.setPlainText("Limit має бути цілим числом більше 0.")
            return

        self.start_button.setEnabled(False)
        self.output.setPlainText("Start Backtest")
        QApplication.processEvents()

        try:
            provider = BinanceMarketDataProvider(base_url=self.config.binance_base_url)
            historical = HistoricalDataProvider(provider)
            candles = historical.get_candles(
                symbol=self.config.symbol,
                interval=interval,
                limit=limit,
            )

            backtest_engine = BacktestEngine(self.config)
            result, trades = backtest_engine.run(candles)

            equity_engine = EquityAnalyticsEngine()
            equity_points = equity_engine.build_equity_points(backtest_engine.last_equity_curve)
            periods = equity_engine.build_period_analytics(backtest_engine.last_equity_curve, trades)
            insights = BacktestInsightsEngine().build_insights(result, periods)

            run_id = self.database.save_backtest_result(result, trades)
            self.database.save_backtest_equity_points(run_id, equity_points)
            self.database.save_backtest_period_analytics(run_id, periods)

            exporter = BacktestReportExporter()
            summary_path = exporter.export_summary_csv(run_id, result)
            trades_path = exporter.export_trades_csv(run_id, result, trades)
            equity_path = exporter.export_equity_csv(run_id, equity_points)
            periods_path = exporter.export_period_analytics_csv(run_id, periods)
            insights_path = BacktestInsightsExporter().export_txt(run_id, insights)

            lines = [
                "Backtest completed",
                f"Run ID: {run_id}",
                f"Symbol: {result.symbol}",
                f"Interval: {result.interval}",
                f"Candles: {result.candles}",
                f"Signals: {result.signals}",
                f"Trades: {result.trades}",
                f"Winning trades: {result.winning_trades}",
                f"Losing trades: {result.losing_trades}",
                f"Win rate: {result.win_rate * 100:.2f}%",
                f"Gross profit: {result.gross_profit:.8f}",
                f"Fees: {result.total_fees:.8f}",
                f"Net profit: {result.net_profit:.8f}",
                f"ROI: {result.roi * 100:.4f}%",
                f"Max drawdown: {result.max_drawdown * 100:.4f}%",
                f"Sharpe: {result.sharpe_ratio:.4f}",
                f"Sortino: {result.sortino_ratio:.4f}",
                f"Profit factor: {result.profit_factor:.4f}",
                f"Expectancy: {result.expectancy:.8f}",
                f"Rating: {insights.rating}",
                f"Summary: {insights.summary}",
                f"Summary CSV: {summary_path}",
                f"Trades CSV: {trades_path}",
                f"Equity CSV: {equity_path}",
                f"Periods CSV: {periods_path}",
                f"Insights TXT: {insights_path}",
                "",
                "--- Updated Backtest Runs ---",
                *self._build_summary_lines(),
            ]
            self.output.setPlainText("\n".join(lines))
        except Exception as exc:
            self.logger.exception("Backtest failed from GUI")
            self.output.setPlainText(f"ERROR:\n{exc}")
        finally:
            self.start_button.setEnabled(True)

    def _build_summary_lines(self) -> list[str]:
        rows = self.database.load_recent_backtest_runs(limit=10)
        if not rows:
            return ["Backtest-запусків ще немає."]

        lines = ["=== Recent Backtest Runs ==="]
        for row in rows:
            run_id, timestamp, symbol, interval, candles, trades, win_rate, net_profit, roi, max_drawdown = row
            lines.append(
                f"#{run_id} | {timestamp} | {symbol} {interval} | "
                f"candles={candles} trades={trades} win={win_rate * 100:.2f}% "
                f"net={net_profit:.8f} roi={roi * 100:.4f}% dd={max_drawdown * 100:.4f}%"
            )
        return lines


class PaperTradingTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.logger = logging.getLogger("usdt_usdc_bot")

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.iterations_input = QLineEdit("10")
        self.iterations_input.setPlaceholderText("Iterations")

        self.start_button = QPushButton("Start Paper Simulation")
        self.start_button.clicked.connect(self.run_paper_simulation)

        self.refresh_button = QPushButton("Показати Paper Summary")
        self.refresh_button.clicked.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Iterations:"))
        controls.addWidget(self.iterations_input)
        controls.addWidget(self.start_button)
        controls.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.refresh_button)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self.output.setPlainText("\n".join(self._build_summary_lines()))

    def run_paper_simulation(self) -> None:
        raw_value = self.iterations_input.text().strip()

        try:
            iterations = int(raw_value)
        except ValueError:
            self.output.setPlainText("Iterations має бути цілим числом більше 0.")
            return

        if iterations <= 0:
            self.output.setPlainText("Iterations має бути цілим числом більше 0.")
            return

        self.start_button.setEnabled(False)
        self.output.setPlainText("Start Paper Simulation")
        QApplication.processEvents()

        try:
            result = PaperTradingEngine(self.config, self.database).run(iterations)
            lines = [
                "Paper simulation completed",
                f"Iterations: {result.iterations}",
                f"Opened cycles: {result.opened_cycles}",
                f"Closed cycles: {result.closed_cycles}",
                f"Safety stops: {result.safety_stops}",
                f"Final USDT: {result.final_portfolio.usdt:.8f}",
                f"Final USDC: {result.final_portfolio.usdc:.8f}",
                f"Final value: {result.final_portfolio.total_value:.8f}",
                "",
                "--- Updated Paper Data ---",
                *self._build_summary_lines(),
            ]
            self.output.setPlainText("\n".join(lines))
        except Exception as exc:
            self.logger.exception("Paper simulation failed from GUI")
            self.output.setPlainText(f"ERROR:\n{exc}")
        finally:
            self.start_button.setEnabled(True)

    def _build_summary_lines(self) -> list[str]:
        cycles = self.database.load_recent_paper_cycles(limit=10)
        runs = self.database.load_recent_paper_runs(limit=10)

        lines = ["=== Paper Trading ===", ""]
        lines.append("Recent Paper Runs:")
        if runs:
            for row in runs:
                run_id, timestamp, iterations, opened, closed, stops, usdt, usdc, value, rating, summary = row
                lines.append(
                    f"#{run_id} | {timestamp} | iter={iterations} opened={opened} "
                    f"closed={closed} stops={stops} value={value:.8f} rating={rating}"
                )
        else:
            lines.append("Paper runs ще немає.")

        lines.append("")
        lines.append("Recent Paper Cycles:")
        if cycles:
            for row in cycles:
                timestamp, cycle_id, direction, status, open_price, close_price, quantity, open_fee, close_fee, gross, net = row
                lines.append(
                    f"{timestamp} | cycle={cycle_id} {direction} {status} "
                    f"open={open_price:.8f} close={close_price:.8f} net={net:.8f}"
                )
        else:
            lines.append("Paper cycles ще немає.")

        return lines


class LogsTab(QWidget):
    def __init__(self, log_file_path: str) -> None:
        super().__init__()
        self.log_file_path = log_file_path

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton("Оновити logs/bot.log")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout()
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        path = Path(self.log_file_path)
        if not path.exists():
            self.output.setPlainText("Лог-файл ще не створено.")
            return

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        self.output.setPlainText("\n".join(lines[-200:]))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.config = ConfigManager().config
        self.database = DatabaseManager(self.config.database_path)

        self.setWindowTitle("USDT/USDC Bot MVP")
        self.resize(1000, 700)

        tabs = QTabWidget()
        tabs.addTab(DashboardTab(self.config, self.database), "Dashboard")
        tabs.addTab(HealthTab(self.config, self.database), "Health")
        tabs.addTab(BacktestTab(self.config, self.database), "Backtest")
        tabs.addTab(PaperTradingTab(self.config, self.database), "Paper Trading")
        tabs.addTab(LogsTab(self.config.log_file_path), "Logs")

        self.setCentralWidget(tabs)
