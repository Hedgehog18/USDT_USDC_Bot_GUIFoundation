import logging
from pathlib import Path

from PySide6.QtCore import Qt
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
from storage.database_manager import DatabaseManager


class PaperTradingTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.logger = logging.getLogger("usdt_usdc_bot")

        self.result_output = self._create_readonly_text(180)
        self.insights_output = self._create_readonly_text(160)
        self.runs_output = self._create_readonly_text(190)
        self.cycles_output = self._create_readonly_text(220)
        self.output = self.result_output

        self.iterations_input = QLineEdit("10")
        self.iterations_input.setPlaceholderText("Iterations")

        self.start_button = QPushButton("Start Paper Simulation")
        self.start_button.clicked.connect(self.run_paper_simulation)

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

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self._section("Result Output", self.result_output))
        top_splitter.addWidget(self._section("Latest Paper Insights", self.insights_output))
        top_splitter.setSizes([620, 520])

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(self._section("Recent Paper Runs", self.runs_output))
        bottom_splitter.addWidget(self._section("Recent Paper Cycles", self.cycles_output))
        bottom_splitter.setSizes([560, 620])

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([310, 430])

        layout = QVBoxLayout()
        layout.addWidget(controls_group)
        layout.addWidget(self.refresh_button)
        layout.addWidget(main_splitter)
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
