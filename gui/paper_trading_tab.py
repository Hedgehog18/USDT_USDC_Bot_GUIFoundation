import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from paper.paper_analytics_engine import PaperAnalyticsEngine
from paper.paper_insights_engine import PaperInsightsEngine
from paper.paper_insights_exporter import PaperInsightsExporter
from paper.paper_report_exporter import PaperReportExporter
from paper.paper_trading_engine import PaperTradingEngine
from paper.long_paper_run_workflow import LongPaperRunWorkflow
from storage.database_manager import DatabaseManager


class LongPaperRunWorker(QObject):
    status = Signal(str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, config, database: DatabaseManager, iterations: int, interval_seconds: int) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.iterations = iterations
        self.interval_seconds = interval_seconds

    @Slot()
    def run(self) -> None:
        try:
            self.status.emit(
                f"Starting long paper run: iterations={self.iterations}, "
                f"interval_seconds={self.interval_seconds}"
            )
            result = LongPaperRunWorkflow(self.config, self.database).run(
                iterations=self.iterations,
                interval_seconds=self.interval_seconds,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class PaperTradingTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.logger = logging.getLogger("usdt_usdc_bot")
        self.long_thread: QThread | None = None
        self.long_worker: LongPaperRunWorker | None = None

        self.result_output = self._create_readonly_text(180)
        self.insights_output = self._create_readonly_text(160)
        self.runs_output = self._create_readonly_text(190)
        self.cycles_output = self._create_readonly_text(220)
        self.output = self.result_output

        self.iterations_input = QLineEdit("10")
        self.iterations_input.setPlaceholderText("Iterations")
        self.long_iterations_input = QLineEdit("500")
        self.long_iterations_input.setPlaceholderText("Long run iterations")
        self.long_interval_input = QLineEdit("5")
        self.long_interval_input.setPlaceholderText("Interval seconds")

        self.start_button = QPushButton("Start Paper Simulation")
        self.start_button.clicked.connect(self.run_paper_simulation)
        self.long_start_button = QPushButton("Start Long Paper Run")
        self.long_start_button.clicked.connect(self.start_long_paper_run)

        self.refresh_button = QPushButton("Refresh Paper Summary")
        self.refresh_button.clicked.connect(self.refresh)

        self.export_button = QPushButton("Export Paper Report")
        self.export_button.clicked.connect(self.export_paper_report)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Iterations:"))
        controls.addWidget(self.iterations_input)
        controls.addWidget(self.start_button)
        controls.addWidget(self.export_button)
        controls.addStretch()

        controls_group = QGroupBox("Paper Simulation Controls")
        controls_group.setLayout(controls)

        long_controls = QHBoxLayout()
        long_controls.addWidget(QLabel("Iterations:"))
        long_controls.addWidget(self.long_iterations_input)
        long_controls.addWidget(QLabel("Interval seconds:"))
        long_controls.addWidget(self.long_interval_input)
        long_controls.addWidget(self.long_start_button)
        long_controls.addStretch()

        long_controls_group = QGroupBox("Long Paper Run")
        long_layout = QVBoxLayout()
        warning = QLabel("Long paper run may take time. Real trading disabled.")
        warning.setStyleSheet("font-weight: 600; color: #f59e0b;")
        long_layout.addWidget(warning)
        long_layout.addLayout(long_controls)
        long_controls_group.setLayout(long_layout)

        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.setObjectName("paper_trading_top_splitter")
        self.top_splitter.addWidget(self._section("Result Output", self.result_output))
        self.top_splitter.addWidget(self._section("Latest Paper Insights", self.insights_output))
        self.top_splitter.setSizes([620, 520])

        self.bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.bottom_splitter.setObjectName("paper_trading_bottom_splitter")
        self.bottom_splitter.addWidget(self._section("Recent Paper Runs", self.runs_output))
        self.bottom_splitter.addWidget(self._section("Recent Paper Cycles", self.cycles_output))
        self.bottom_splitter.setSizes([560, 620])

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setObjectName("paper_trading_main_splitter")
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.bottom_splitter)
        self.main_splitter.setSizes([310, 430])

        layout = QVBoxLayout()
        layout.addWidget(controls_group)
        layout.addWidget(long_controls_group)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.main_splitter)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self.result_output.setPlainText("Ready. Use Start Paper Simulation or Export Paper Report.")
        self.insights_output.setPlainText("\n".join(self._latest_paper_insights_lines()))
        self.runs_output.setPlainText("\n".join(self._paper_runs_lines()))
        self.cycles_output.setPlainText("\n".join(self._paper_cycles_lines()))

    def run_paper_simulation(self) -> None:
        raw_value = self.iterations_input.text().strip()

        try:
            iterations = int(raw_value)
        except ValueError:
            self.result_output.setPlainText("Iterations має бути цілим числом більше 0.")
            return

        if iterations <= 0:
            self.result_output.setPlainText("Iterations має бути цілим числом більше 0.")
            return

        self.start_button.setEnabled(False)
        self.result_output.setPlainText("Start Paper Simulation")
        QApplication.processEvents()

        try:
            result = PaperTradingEngine(self.config, self.database).run(iterations)
            cycle_rows = self.database.load_recent_paper_cycles(limit=500)
            safety_rows = self.database.load_recent_paper_safety_events(limit=500)
            stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)
            insights = PaperInsightsEngine().build(stats, safety_rows)
            paper_run_id = self.database.save_paper_run(result, insights)
            insights_path = PaperInsightsExporter().export_txt(paper_run_id, insights)
            lines = [
                "Paper simulation completed",
                f"Run ID: {paper_run_id}",
                f"Iterations: {result.iterations}",
                f"Opened cycles: {result.opened_cycles}",
                f"Closed cycles: {result.closed_cycles}",
                f"Safety stops: {result.safety_stops}",
                f"Final USDT: {result.final_portfolio.usdt:.8f}",
                f"Final USDC: {result.final_portfolio.usdc:.8f}",
                f"Final value: {result.final_portfolio.total_value:.8f}",
                f"Insights TXT: {insights_path}",
                f"Rating: {insights.rating}",
                f"Summary: {insights.summary}",
            ]
            self.refresh()
            self.result_output.setPlainText("\n".join(lines))
        except Exception as exc:
            self.logger.exception("Paper simulation failed from GUI")
            self.result_output.setPlainText(f"ERROR:\n{exc}")
        finally:
            self.start_button.setEnabled(True)

    def start_long_paper_run(self) -> None:
        iterations = self._read_positive_int(self.long_iterations_input.text(), "Iterations")
        if iterations is None:
            return

        interval_seconds = self._read_non_negative_int(self.long_interval_input.text(), "Interval seconds")
        if interval_seconds is None:
            return

        if self.long_thread is not None:
            self.result_output.setPlainText("Long paper run is already running.")
            return

        self.long_start_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.result_output.setPlainText(
            "Long paper run started.\n"
            "Long paper run may take time. Real trading disabled."
        )

        self.long_thread = QThread(self)
        self.long_worker = LongPaperRunWorker(self.config, self.database, iterations, interval_seconds)
        self.long_worker.moveToThread(self.long_thread)
        self.long_thread.started.connect(self.long_worker.run)
        self.long_worker.status.connect(self.result_output.setPlainText)
        self.long_worker.finished.connect(self._handle_long_paper_finished)
        self.long_worker.error.connect(self._handle_long_paper_error)
        self.long_worker.finished.connect(self.long_thread.quit)
        self.long_worker.error.connect(self.long_thread.quit)
        self.long_thread.finished.connect(self.long_worker.deleteLater)
        self.long_thread.finished.connect(self._clear_long_paper_thread)
        self.long_thread.start()

    def _handle_long_paper_finished(self, result) -> None:
        lines = [
            "Long paper run completed",
            "Real trading disabled.",
            f"Run ID: {result.run_id}",
            f"Iterations: {result.run_result.iterations}",
            f"Opened cycles: {result.run_result.opened_cycles}",
            f"Closed cycles: {result.run_result.closed_cycles}",
            f"Safety stops: {result.run_result.safety_stops}",
            f"Final value: {result.run_result.final_portfolio.total_value:.8f}",
            "",
            "Paper Stats:",
            f"Total cycles: {result.stats.total_cycles}",
            f"Closed cycles: {result.stats.closed_cycles}",
            f"Win rate: {result.stats.win_rate * 100:.2f}%",
            f"Net profit: {result.stats.net_profit:.8f}",
            f"Profit factor: {result.stats.profit_factor:.4f}",
            "",
            "Paper Insights:",
            f"Rating: {result.insights.rating}",
            f"Summary: {result.insights.summary}",
            "",
            "Validation Summary:",
            f"Overall status: {result.validation_summary.overall_status}",
            f"Next action: {result.validation_summary.next_action}",
            "",
            "Reports:",
            f"Cycles CSV: {result.report_paths.cycles_csv}",
            f"Safety CSV: {result.report_paths.safety_csv}",
            f"Summary CSV: {result.report_paths.summary_csv}",
            f"Insights TXT: {result.report_paths.insights_txt}",
        ]
        self.refresh()
        self.result_output.setPlainText("\n".join(lines))

    def _handle_long_paper_error(self, message: str) -> None:
        self.logger.error("Long paper run failed from GUI: %s", message)
        self.result_output.setPlainText(f"ERROR:\n{message}")

    def _clear_long_paper_thread(self) -> None:
        self.long_thread = None
        self.long_worker = None
        self.long_start_button.setEnabled(True)
        self.start_button.setEnabled(True)

    def export_paper_report(self) -> None:
        try:
            cycle_rows = self.database.load_recent_paper_cycles(limit=500)
            safety_rows = self.database.load_recent_paper_safety_events(limit=500)
            stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)

            exporter = PaperReportExporter()
            cycles_path = exporter.export_cycles_csv(cycle_rows)
            safety_path = exporter.export_safety_csv(safety_rows)
            summary_path = exporter.export_summary_csv(stats)

            lines = [
                "Paper report exported",
                f"Cycles CSV: {cycles_path}",
                f"Safety CSV: {safety_path}",
                f"Summary CSV: {summary_path}",
            ]
            self.refresh()
            self.result_output.setPlainText("\n".join(lines))
        except Exception as exc:
            self.logger.exception("Paper report export failed from GUI")
            self.result_output.setPlainText(f"ERROR:\n{exc}")

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

    def _read_positive_int(self, raw_value: str, label: str) -> int | None:
        try:
            value = int(raw_value.strip())
        except ValueError:
            self.result_output.setPlainText(f"{label} must be an integer greater than 0.")
            return None
        if value <= 0:
            self.result_output.setPlainText(f"{label} must be an integer greater than 0.")
            return None
        return value

    def _read_non_negative_int(self, raw_value: str, label: str) -> int | None:
        try:
            value = int(raw_value.strip())
        except ValueError:
            self.result_output.setPlainText(f"{label} must be an integer 0 or greater.")
            return None
        if value < 0:
            self.result_output.setPlainText(f"{label} must be an integer 0 or greater.")
            return None
        return value

    def _build_summary_lines(self) -> list[str]:
        lines = ["=== Paper Trading ===", ""]
        lines.append("Latest Paper Insights:")
        lines.extend(self._latest_paper_insights_lines())
        lines.append("")
        lines.append("Recent Paper Runs:")
        lines.extend(self._paper_runs_lines())
        lines.append("")
        lines.append("Recent Paper Cycles:")
        lines.extend(self._paper_cycles_lines())
        return lines

    def _paper_runs_lines(self) -> list[str]:
        runs = self.database.load_recent_paper_runs(limit=10)
        lines = []
        if runs:
            for row in runs:
                run_id, timestamp, iterations, opened, closed, stops, usdt, usdc, value, rating, summary = row
                lines.append(
                    f"#{run_id} | {timestamp} | iter={iterations} opened={opened} "
                    f"closed={closed} stops={stops} value={value:.8f} rating={rating}"
                )
        else:
            lines.append("Paper runs ще немає.")
        return lines

    def _paper_cycles_lines(self) -> list[str]:
        cycles = self.database.load_recent_paper_cycles(limit=10)
        lines = []
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

    def _latest_paper_insights_lines(self) -> list[str]:
        rows = self.database.load_recent_paper_runs(limit=1)
        if rows:
            run_id, _timestamp, _iterations, _opened, _closed, _stops, _usdt, _usdc, _value, rating, summary = rows[0]
            path = Path("reports") / f"paper_run_{run_id}_insights.txt"
            if path.exists():
                return [f"Insights TXT: {path}", *path.read_text(encoding="utf-8", errors="replace").splitlines()]
            return [
                f"Run ID: {run_id}",
                f"Rating: {rating}",
                f"Summary: {summary}",
                "Insights TXT: not found yet.",
            ]

        cycle_rows = self.database.load_recent_paper_cycles(limit=500)
        safety_rows = self.database.load_recent_paper_safety_events(limit=500)
        stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)
        insights = PaperInsightsEngine().build(stats, safety_rows)
        return [
            "No saved paper runs yet. Current data estimate:",
            f"Rating: {insights.rating}",
            f"Summary: {insights.summary}",
        ]
