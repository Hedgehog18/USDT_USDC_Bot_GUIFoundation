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

from config.config_manager import ConfigManager
from health.health_check import HealthCheck
from paper.paper_trading_engine import PaperTradingEngine
from storage.database_manager import DatabaseManager


class DashboardTab(QWidget):
    def __init__(self, database: DatabaseManager) -> None:
        super().__init__()
        self.database = database

        self.status_label = QLabel("Status: ready")
        self.stats_label = QLabel("")
        self.refresh_button = QPushButton("Оновити Dashboard")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("USDT/USDC Bot MVP"))
        layout.addWidget(self.status_label)
        layout.addWidget(self.stats_label)
        layout.addWidget(self.refresh_button)
        layout.addStretch()
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        cycles = self.database.count_rows("cycles")
        signals = self.database.count_rows("trade_signals")
        paper_cycles = self.database.count_rows("paper_cycles")
        paper_runs = self.database.count_rows("paper_runs")

        self.stats_label.setText(
            f"Cycles: {cycles}\n"
            f"Signals: {signals}\n"
            f"Paper cycles: {paper_cycles}\n"
            f"Paper runs: {paper_runs}"
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
    def __init__(self, database: DatabaseManager) -> None:
        super().__init__()
        self.database = database

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton("Показати останні Backtest Runs")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout()
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        rows = self.database.load_recent_backtest_runs(limit=10)
        if not rows:
            self.output.setPlainText("Backtest-запусків ще немає.")
            return

        lines = ["=== Recent Backtest Runs ==="]
        for row in rows:
            run_id, timestamp, symbol, interval, candles, trades, win_rate, net_profit, roi, max_drawdown = row
            lines.append(
                f"#{run_id} | {timestamp} | {symbol} {interval} | "
                f"candles={candles} trades={trades} win={win_rate * 100:.2f}% "
                f"net={net_profit:.8f} roi={roi * 100:.4f}% dd={max_drawdown * 100:.4f}%"
            )
        self.output.setPlainText("\n".join(lines))


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
        tabs.addTab(DashboardTab(self.database), "Dashboard")
        tabs.addTab(HealthTab(self.config, self.database), "Health")
        tabs.addTab(BacktestTab(self.database), "Backtest")
        tabs.addTab(PaperTradingTab(self.config, self.database), "Paper Trading")
        tabs.addTab(LogsTab(self.config.log_file_path), "Logs")

        self.setCentralWidget(tabs)
