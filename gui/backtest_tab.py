import logging

from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from backtest.backtest_engine import BacktestEngine
from backtest.backtest_insights_engine import BacktestInsightsEngine
from backtest.backtest_insights_exporter import BacktestInsightsExporter
from backtest.backtest_report_exporter import BacktestReportExporter
from backtest.equity_analytics_engine import EquityAnalyticsEngine
from backtest.historical_data_provider import HistoricalDataProvider
from market.binance_market_data_provider import BinanceMarketDataProvider
from storage.database_manager import DatabaseManager


class BacktestTab(QWidget):
    ALLOWED_INTERVALS = ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d")

    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.logger = logging.getLogger("usdt_usdc_bot")

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.interval_input = QComboBox()
        self.interval_input.addItems(self.ALLOWED_INTERVALS)
        configured_interval = self.config.backtest_interval or "1m"
        self.interval_input.setCurrentText(
            configured_interval if configured_interval in self.ALLOWED_INTERVALS else "1m"
        )

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
        interval = self.interval_input.currentText().strip()
        raw_limit = self.limit_input.text().strip()

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

