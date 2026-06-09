import logging

from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from paper.paper_trading_engine import PaperTradingEngine
from storage.database_manager import DatabaseManager


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
