from datetime import datetime
from enum import Enum
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


class RunnerStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


def can_start_runner(status: RunnerStatus, mode: str) -> tuple[bool, str]:
    if status in {RunnerStatus.RUNNING, RunnerStatus.STOPPING}:
        return False, "Runner is already active."
    if mode.upper() == "REAL":
        return False, "Start Demo Runner is blocked in REAL mode."
    return True, ""


def can_stop_runner(status: RunnerStatus) -> tuple[bool, str]:
    if status != RunnerStatus.RUNNING:
        return False, "Runner is not running."
    return True, ""


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
    def __init__(self, config, database: DatabaseManager, dashboard_refresh_callback=None) -> None:
        super().__init__()
        self.config = config
        self.database = database
        self.dashboard_refresh_callback = dashboard_refresh_callback
        self.thread: QThread | None = None
        self.worker: DemoRunnerWorker | None = None
        self.status = RunnerStatus.IDLE
        self.stopped_by_user = False

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

        self.status_label = QLabel(f"Runner status: {self.status.value}")

        self.summary_output = QTextEdit()
        self.summary_output.setReadOnly(True)
        self.summary_output.setMaximumHeight(105)

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
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Status:"))
        layout.addWidget(self.status_output)
        layout.addWidget(QLabel("Last run summary:"))
        layout.addWidget(self.summary_output)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Monitor:"))
        layout.addWidget(self.output)
        self.setLayout(layout)

        self._update_last_run_summary()
        self._set_status(RunnerStatus.IDLE)
        self.refresh()

    def start_demo_runner(self) -> None:
        can_start, reason = can_start_runner(self.status, str(getattr(self.config, "mode", "")))
        if not can_start:
            self._append_status(f"WARNING: {reason}")
            return

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
        self.stopped_by_user = False
        self._set_status(RunnerStatus.RUNNING)
        self._update_last_run_summary()
        self._save_system_event("INFO", "runner started from GUI")

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
        can_stop, reason = can_stop_runner(self.status)
        if not can_stop or self.worker is None:
            self._append_status(f"WARNING: {reason}")
            return

        self.stopped_by_user = True
        self._set_status(RunnerStatus.STOPPING)
        self.stop_button.setEnabled(False)
        self._append_status("Stop requested by user.")
        self._save_system_event("WARNING", "runner stop requested from GUI")
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

    def _set_status(self, status: RunnerStatus) -> None:
        self.status = status
        self.status_label.setText(f"Runner status: {self.status.value}")

        mode_is_real = str(getattr(self.config, "mode", "")).upper() == "REAL"
        active = status in {RunnerStatus.RUNNING, RunnerStatus.STOPPING}
        self.start_button.setEnabled(not active and not mode_is_real)
        self.stop_button.setEnabled(status == RunnerStatus.RUNNING)
        self.iterations_input.setEnabled(not active)
        self.interval_input.setEnabled(not active)

        if mode_is_real:
            self.start_button.setToolTip("Start Demo Runner is blocked in REAL mode.")
        else:
            self.start_button.setToolTip("")

    def _append_status(self, message: str) -> None:
        if not message:
            return
        current = self.status_output.toPlainText()
        line = f"{datetime.now().isoformat(timespec='seconds')} | {clean_display_text(message)}"
        self.status_output.setPlainText(f"{current}\n{line}".strip())
        self.status_output.verticalScrollBar().setValue(self.status_output.verticalScrollBar().maximum())

    def _handle_runner_finished(self, iterations_completed: int, stopped_by_limit: bool) -> None:
        self._set_status(RunnerStatus.FINISHED)
        self._append_status(
            "Demo runner completed. "
            f"Iterations: {iterations_completed}. Stopped by limit: {stopped_by_limit}."
        )
        self._update_last_run_summary(
            iterations_completed=iterations_completed,
            stopped_by_limit=stopped_by_limit,
            stopped_by_user=self.stopped_by_user,
        )
        self._save_system_event(
            "INFO",
            (
                "runner finished from GUI: "
                f"iterations={iterations_completed}, "
                f"stopped_by_limit={stopped_by_limit}, "
                f"stopped_by_user={self.stopped_by_user}"
            ),
        )
        self._refresh_after_runner()

    def _handle_runner_error(self, message: str) -> None:
        self._set_status(RunnerStatus.ERROR)
        self._append_status(f"ERROR:\n{message}")
        self._update_last_run_summary(
            iterations_completed=0,
            stopped_by_limit=False,
            stopped_by_user=self.stopped_by_user,
            error_message=message,
        )
        self._save_system_event("ERROR", f"runner error from GUI: {message}")
        self._refresh_after_runner()

    def _clear_runner_thread(self) -> None:
        self.thread = None
        self.worker = None

    def _update_last_run_summary(
        self,
        iterations_completed: int | None = None,
        stopped_by_limit: bool | None = None,
        stopped_by_user: bool | None = None,
        error_message: str | None = None,
    ) -> None:
        lines = [
            f"Iterations completed: {iterations_completed if iterations_completed is not None else 'N/A'}",
            f"Stopped by limit: {stopped_by_limit if stopped_by_limit is not None else 'N/A'}",
            f"Stopped by user: {stopped_by_user if stopped_by_user is not None else 'N/A'}",
            f"Error message: {clean_display_text(error_message) if error_message else 'N/A'}",
        ]
        self.summary_output.setPlainText("\n".join(lines))

    def _save_system_event(self, level: str, message: str) -> None:
        try:
            self.database.save_system_event(level, "RunnerTab", message)
        except Exception:
            pass

    def _refresh_after_runner(self) -> None:
        try:
            self.refresh()
        except Exception:
            pass

        if self.dashboard_refresh_callback is None:
            return

        try:
            self.dashboard_refresh_callback()
        except Exception:
            pass

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
