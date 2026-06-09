from datetime import datetime
import traceback

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.bot_engine import BotEngine
from runner.bot_runner import BotRunner
from storage.database_manager import DatabaseManager


MOJIBAKE_MARKERS = ("Р", "СЃ", "С–", "С€", "Ð", "Ñ", "Ò")


def clean_display_text(value) -> str:
    text = str(value)
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text

    candidates = [text]
    for source_encoding, target_encoding in (("cp1251", "utf-8"), ("cp1252", "cp1251")):
        try:
            candidates.append(text.encode(source_encoding).decode(target_encoding))
        except UnicodeError:
            pass

    return min(candidates, key=_mojibake_score)


def _mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in MOJIBAKE_MARKERS)


class _SignalWriter:
    def __init__(self, signal: Signal) -> None:
        self.signal = signal
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.signal.emit(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            self.signal.emit(self._buffer.strip())
        self._buffer = ""


class DemoRunnerWorker(QObject):
    started = Signal(str)
    status = Signal(str)
    finished = Signal(int, bool)
    error = Signal(str)

    def __init__(self, iterations: int, interval_seconds: int) -> None:
        super().__init__()
        self.iterations = iterations
        self.interval_seconds = interval_seconds
        self.runner: BotRunner | None = None
        self._stop_requested = False

    @Slot()
    def run(self) -> None:
        try:
            self.status.emit("Creating demo runner...")
            bot = BotEngine()
            self.runner = BotRunner(
                bot=bot,
                interval_seconds=self.interval_seconds,
                max_iterations=self.iterations,
            )

            if self._stop_requested:
                self.runner.request_stop()

            self.started.emit("Demo runner started.")
            writer = _SignalWriter(self.status)

            import contextlib

            with contextlib.redirect_stdout(writer):
                result = self.runner.run()
            writer.flush()

            self.finished.emit(result.iterations_completed, result.stopped_by_limit)
        except Exception:
            self.error.emit(traceback.format_exc())

    def request_stop(self) -> None:
        self._stop_requested = True
        if self.runner is not None:
            self.runner.request_stop()
        self.status.emit("Stop requested. Runner will stop safely.")


class RunnerTab(QWidget):
    def __init__(self, config, database: DatabaseManager) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.thread: QThread | None = None
        self.worker: DemoRunnerWorker | None = None

        self.iterations_input = QLineEdit(str(getattr(self.config, "max_runner_iterations", 5)))
        self.interval_input = QLineEdit(str(getattr(self.config, "runner_interval_seconds", 10)))

        self.start_button = QPushButton("Start Demo Runner")
        self.start_button.clicked.connect(self.start_demo_runner)

        self.stop_button = QPushButton("Stop Runner")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_runner)

        self.status_output = QTextEdit()
        self.status_output.setReadOnly(True)
        self.status_output.setMaximumHeight(170)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton("Refresh Runner")
        self.refresh_button.clicked.connect(self.refresh)

        self.auto_refresh_checkbox = QCheckBox("Auto Refresh")
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Iterations:"))
        controls.addWidget(self.iterations_input)
        controls.addWidget(QLabel("Interval seconds:"))
        controls.addWidget(self.interval_input)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)

        actions = QHBoxLayout()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.auto_refresh_checkbox)
        actions.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(QLabel("Status:"))
        layout.addWidget(self.status_output)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Monitor:"))
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def start_demo_runner(self) -> None:
        iterations = self._read_positive_int(self.iterations_input.text(), "Iterations")
        if iterations is None:
            return

        interval_seconds = self._read_positive_int(self.interval_input.text(), "Interval seconds")
        if interval_seconds is None:
            return

        self.status_output.clear()
        self._append_status(
            f"Starting demo runner: iterations={iterations}, interval_seconds={interval_seconds}"
        )
        self._set_running_state(True)

        self.thread = QThread(self)
        self.worker = DemoRunnerWorker(iterations=iterations, interval_seconds=interval_seconds)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.started.connect(self._append_status)
        self.worker.status.connect(self._append_status)
        self.worker.finished.connect(self._handle_runner_finished)
        self.worker.error.connect(self._handle_runner_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._clear_runner_thread)

        self.thread.start()

    def stop_runner(self) -> None:
        if self.worker is None:
            self._append_status("No runner is currently active.")
            return

        self.stop_button.setEnabled(False)
        self._append_status("Stop requested by user.")
        self.worker.request_stop()

    def refresh(self) -> None:
        lines = [
            "=== System ===",
            f"Mode: {getattr(self.config, 'mode', 'N/A')}",
            f"Symbol: {getattr(self.config, 'symbol', 'N/A')}",
            f"Current Time: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "=== Database Counters ===",
            f"Cycles: {self._safe_count('cycles')}",
            f"Signals: {self._safe_count('trade_signals')}",
            f"Backtest Runs: {self._safe_count('backtest_runs')}",
            f"Paper Runs: {self._safe_count('paper_runs')}",
            f"Paper Safety Events: {self._safe_count('paper_safety_events')}",
            f"System Events: {self._safe_count('system_events')}",
            "",
        ]

        self._append_latest_signal(lines)
        lines.append("")
        self._append_latest_cycle(lines)
        lines.append("")
        self._append_latest_system_event(lines)

        self.output.setPlainText("\n".join(lines))

    def toggle_auto_refresh(self) -> None:
        if self.auto_refresh_checkbox.isChecked():
            self.timer.start()
        else:
            self.timer.stop()

    def _read_positive_int(self, raw_value: str, label: str) -> int | None:
        try:
            value = int(raw_value.strip())
        except ValueError:
            self.status_output.setPlainText(f"{label} має бути цілим числом більше 0.")
            return None

        if value <= 0:
            self.status_output.setPlainText(f"{label} має бути цілим числом більше 0.")
            return None

        return value

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.iterations_input.setEnabled(not running)
        self.interval_input.setEnabled(not running)

    def _append_status(self, message: str) -> None:
        if not message:
            return
        current = self.status_output.toPlainText()
        line = f"{datetime.now().isoformat(timespec='seconds')} | {clean_display_text(message)}"
        self.status_output.setPlainText(f"{current}\n{line}".strip())
        self.status_output.verticalScrollBar().setValue(self.status_output.verticalScrollBar().maximum())

    def _handle_runner_finished(self, iterations_completed: int, stopped_by_limit: bool) -> None:
        self._append_status(
            "Demo runner completed. "
            f"Iterations: {iterations_completed}. Stopped by limit: {stopped_by_limit}."
        )
        self._set_running_state(False)
        self.refresh()

    def _handle_runner_error(self, message: str) -> None:
        self._append_status(f"ERROR:\n{message}")
        try:
            self.database.save_system_event("ERROR", "RunnerTab", message)
        except Exception:
            pass
        self._set_running_state(False)
        self.refresh()

    def _clear_runner_thread(self) -> None:
        self.thread = None
        self.worker = None

    def _safe_count(self, table_name: str) -> int:
        try:
            return self.database.count_rows(table_name)
        except Exception:
            return 0

    def _append_latest_signal(self, lines: list[str]) -> None:
        lines.append("=== Latest Signal ===")
        try:
            row = self.database.load_latest_signal()
        except Exception as exc:
            lines.append(f"Could not load latest signal: {exc}")
            return

        if not row:
            lines.append("No signals yet.")
            return

        timestamp, decision, confidence, reason = row
        lines.extend([
            f"Timestamp: {timestamp}",
            f"Decision: {clean_display_text(decision)}",
            f"Confidence: {clean_display_text(confidence)}",
            f"Reason: {clean_display_text(reason)}",
        ])

    def _append_latest_cycle(self, lines: list[str]) -> None:
        lines.append("=== Latest Cycle ===")
        try:
            row = self.database.load_latest_cycle()
        except Exception as exc:
            lines.append(f"Could not load latest cycle: {exc}")
            return

        if not row:
            lines.append("No cycles yet.")
            return

        cycle_id, direction, status, open_price, close_price, pnl = row
        lines.extend([
            f"Cycle ID: {cycle_id}",
            f"Direction: {direction}",
            f"Status: {status}",
            f"Open Price: {open_price:.8f}",
            f"Close Price: {close_price:.8f}",
            f"PnL: {self._format_optional_float(pnl)}",
        ])

    def _append_latest_system_event(self, lines: list[str]) -> None:
        lines.append("=== Latest System Event ===")
        try:
            row = self.database.load_latest_system_event()
        except Exception as exc:
            lines.append(f"Could not load latest system event: {exc}")
            return

        if not row:
            lines.append("No system events yet.")
            return

        timestamp, level, module, message = row
        lines.extend([
            f"Timestamp: {timestamp}",
            f"Level: {clean_display_text(level)}",
            f"Module: {clean_display_text(module)}",
            f"Message: {clean_display_text(message)}",
        ])

    def _format_optional_float(self, value) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.8f}"
