from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from analytics.hf_real_blackbox_engine import HFRealBlackboxDiagnosticsEngine
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFRealCloseWatcherTimelineEvent:
    name: str
    timestamp: str | None
    seconds_from_entry_fill: float | None
    details: str


@dataclass(frozen=True)
class HFRealCloseWatcherTargetCheck:
    timestamp: str
    phase: str | None
    source: str | None
    iteration: int | None
    executable_price: float | None
    bid: float | None
    ask: float | None
    target_price: float
    condition_met: bool
    seconds_from_entry_fill: float | None
    close_trigger_source: str | None


@dataclass(frozen=True)
class HFRealCloseWatcherAffectedCycle:
    db_id: int
    direction: str
    target_price: float
    executable_touch_timestamp: str | None
    first_watcher_check_timestamp: str | None
    fill_to_first_check_seconds: float | None
    entry_snapshot_to_first_check_seconds: float | None
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    net_profit: float


@dataclass(frozen=True)
class HFRealCloseWatcherGapCycleReport:
    db_id: int
    cycle: dict[str, Any] | None
    target_price: float | None
    entry_order_sent_at: str | None
    entry_order_filled_at: str | None
    cycle_created_at: str | None
    first_blackbox_snapshot_at: str | None
    first_executable_touch_at: str | None
    close_watcher_started_at: str | None
    first_target_check_at: str | None
    timeout_order_sent_at: str | None
    timeout_order_filled_at: str | None
    fill_to_close_watcher_start_seconds: float | None
    fill_to_first_target_check_seconds: float | None
    entry_snapshot_to_first_check_seconds: float | None
    executable_target_touched: bool
    real_target_close_triggered: bool
    target_close_order_sent: bool
    target_close_order_filled: bool
    timeline: list[HFRealCloseWatcherTimelineEvent]
    target_checks: list[HFRealCloseWatcherTargetCheck]


@dataclass(frozen=True)
class HFRealCloseWatcherGapDiagnosticsReport:
    profile: str
    cycles_analyzed: int
    executable_touches: int
    immediate_checks_performed: int
    immediate_target_triggers: int
    regular_watcher_triggers: int
    missed_executable_touches: int
    missed_touch_rate: float
    average_fill_to_first_check_delay: float | None
    maximum_fill_to_first_check_delay: float | None
    affected_cycles: list[HFRealCloseWatcherAffectedCycle]
    cycle_report: HFRealCloseWatcherGapCycleReport | None
    recommendation: str


class HFRealCloseWatcherGapDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(
        self,
        profile: str = "mean_reversion_hf_micro_v1",
        *,
        real_cycle_id: int | None = None,
    ) -> HFRealCloseWatcherGapDiagnosticsReport:
        cycles = self._load_real_cycles(profile)
        cycle_reports = [self._build_cycle_report(cycle) for cycle in cycles]
        executable_touch_reports = [report for report in cycle_reports if report.executable_target_touched]
        immediate_check_reports = [
            report for report in cycle_reports
            if any(check.close_trigger_source == "immediate_post_fill" for check in report.target_checks)
        ]
        immediate_target_reports = [
            report for report in cycle_reports
            if report.real_target_close_triggered
            and any(
                check.close_trigger_source == "immediate_post_fill" and check.condition_met
                for check in report.target_checks
            )
        ]
        regular_target_reports = [
            report for report in cycle_reports
            if report.real_target_close_triggered
            and not any(
                check.close_trigger_source == "immediate_post_fill" and check.condition_met
                for check in report.target_checks
            )
        ]
        affected_reports = [
            report for report in executable_touch_reports
            if report.cycle is not None
            and report.cycle.get("close_reason") == "max_holding_270s"
            and not report.real_target_close_triggered
        ]
        affected = [self._affected_cycle_from_report(report) for report in affected_reports if report.cycle is not None]
        delays = [
            report.fill_to_first_target_check_seconds
            for report in cycle_reports
            if report.fill_to_first_target_check_seconds is not None
        ]
        selected = None
        if real_cycle_id is not None:
            selected = next((report for report in cycle_reports if report.db_id == real_cycle_id), None)
            if selected is None:
                selected = HFRealCloseWatcherGapCycleReport(
                    db_id=real_cycle_id,
                    cycle=None,
                    target_price=None,
                    entry_order_sent_at=None,
                    entry_order_filled_at=None,
                    cycle_created_at=None,
                    first_blackbox_snapshot_at=None,
                    first_executable_touch_at=None,
                    close_watcher_started_at=None,
                    first_target_check_at=None,
                    timeout_order_sent_at=None,
                    timeout_order_filled_at=None,
                    fill_to_close_watcher_start_seconds=None,
                    fill_to_first_target_check_seconds=None,
                    entry_snapshot_to_first_check_seconds=None,
                    executable_target_touched=False,
                    real_target_close_triggered=False,
                    target_close_order_sent=False,
                    target_close_order_filled=False,
                    timeline=[],
                    target_checks=[],
                )
        missed = len(affected)
        touch_count = len(executable_touch_reports)
        return HFRealCloseWatcherGapDiagnosticsReport(
            profile=profile,
            cycles_analyzed=len(cycle_reports),
            executable_touches=touch_count,
            immediate_checks_performed=len(immediate_check_reports),
            immediate_target_triggers=len(immediate_target_reports),
            regular_watcher_triggers=len(regular_target_reports),
            missed_executable_touches=missed,
            missed_touch_rate=(missed / touch_count) if touch_count else 0.0,
            average_fill_to_first_check_delay=mean(delays) if delays else None,
            maximum_fill_to_first_check_delay=max(delays) if delays else None,
            affected_cycles=affected,
            cycle_report=selected,
            recommendation=self._recommendation(missed, touch_count, delays),
        )

    def _build_cycle_report(self, cycle: dict[str, Any]) -> HFRealCloseWatcherGapCycleReport:
        db_id = int(cycle["id"])
        direction = str(cycle["direction"])
        target_price = HFRealBlackboxDiagnosticsEngine.target_price(direction, float(cycle["open_price"]))
        snapshots = self.database.load_real_pilot_market_snapshots(db_id)
        checks = self._target_checks(cycle, snapshots, target_price)
        first_blackbox = next((row for row in snapshots if row.get("phase") in {"entry", "tracking", "exit"}), None)
        executable_touch = next((check for check in checks if check.condition_met), None)
        first_check = next((check for check in checks if check.source == "real_pilot_close_watch"), None)
        if first_check is None:
            first_check = next((check for check in checks if check.phase in {"tracking", "exit"}), None)
        entry_sent, entry_filled = self._entry_order_times(cycle)
        timeout_sent, timeout_filled = self._close_order_times(cycle, close_reason="max_holding_270s")
        target_sent, target_filled = self._close_order_times(cycle, close_reason="real_pilot_target")
        close_started = self._close_watcher_started_at(snapshots, first_check)
        timeline = self._timeline(
            entry_sent=entry_sent,
            entry_filled=entry_filled,
            cycle=cycle,
            target_price=target_price,
            first_blackbox=first_blackbox,
            executable_touch=executable_touch,
            close_started=close_started,
            first_check=first_check,
            timeout_sent=timeout_sent,
            timeout_filled=timeout_filled,
        )
        return HFRealCloseWatcherGapCycleReport(
            db_id=db_id,
            cycle=cycle,
            target_price=target_price,
            entry_order_sent_at=entry_sent,
            entry_order_filled_at=entry_filled,
            cycle_created_at=str(cycle.get("opened_at") or cycle.get("timestamp") or ""),
            first_blackbox_snapshot_at=str(first_blackbox.get("timestamp")) if first_blackbox else None,
            first_executable_touch_at=executable_touch.timestamp if executable_touch else None,
            close_watcher_started_at=close_started,
            first_target_check_at=first_check.timestamp if first_check else None,
            timeout_order_sent_at=timeout_sent,
            timeout_order_filled_at=timeout_filled,
            fill_to_close_watcher_start_seconds=_seconds_between(entry_filled, close_started),
            fill_to_first_target_check_seconds=_seconds_between(entry_filled, first_check.timestamp if first_check else None),
            entry_snapshot_to_first_check_seconds=_seconds_between(
                str(first_blackbox.get("timestamp")) if first_blackbox else None,
                first_check.timestamp if first_check else None,
            ),
            executable_target_touched=executable_touch is not None,
            real_target_close_triggered=cycle.get("close_reason") == "real_pilot_target",
            target_close_order_sent=target_sent is not None,
            target_close_order_filled=target_filled is not None,
            timeline=timeline,
            target_checks=checks,
        )

    def _target_checks(
        self,
        cycle: dict[str, Any],
        snapshots: list[dict[str, Any]],
        target_price: float,
    ) -> list[HFRealCloseWatcherTargetCheck]:
        entry_filled = self._entry_order_times(cycle)[1]
        checks = []
        for row in snapshots:
            if row.get("phase") not in {"entry", "tracking", "exit", "post_exit"}:
                continue
            executable = HFRealBlackboxDiagnosticsEngine._executable_close_reference(str(cycle["direction"]), row)
            if executable is None:
                continue
            raw = _json(row.get("raw_payload_json"))
            raw_seconds = _float(raw.get("seconds_since_entry_fill"))
            checks.append(HFRealCloseWatcherTargetCheck(
                timestamp=str(raw.get("target_check_at") or row.get("timestamp")),
                phase=str(row.get("phase")) if row.get("phase") is not None else None,
                source=str(row.get("source")) if row.get("source") is not None else None,
                iteration=_int(raw.get("iteration")),
                executable_price=executable,
                bid=_float(row.get("bid")),
                ask=_float(row.get("ask")),
                target_price=target_price,
                condition_met=HFRealBlackboxDiagnosticsEngine.target_hit(str(cycle["direction"]), executable, target_price),
                seconds_from_entry_fill=raw_seconds if raw_seconds is not None else _seconds_between(entry_filled, str(row.get("timestamp"))),
                close_trigger_source=str(raw.get("close_trigger_source")) if raw.get("close_trigger_source") else None,
            ))
        return sorted(
            checks,
            key=lambda check: (
                normalize_diagnostic_datetime(check.timestamp) is None,
                normalize_diagnostic_datetime(check.timestamp) or datetime.max.replace(tzinfo=timezone.utc),
            ),
        )

    def _affected_cycle_from_report(self, report: HFRealCloseWatcherGapCycleReport) -> HFRealCloseWatcherAffectedCycle:
        metrics = HFRealBlackboxDiagnosticsEngine(self.database).build_report(
            profile=str(report.cycle["strategy_profile"]),
            real_cycle_id=report.db_id,
        ).metrics
        return HFRealCloseWatcherAffectedCycle(
            db_id=report.db_id,
            direction=str(report.cycle["direction"]),
            target_price=float(report.target_price or 0.0),
            executable_touch_timestamp=report.first_executable_touch_at,
            first_watcher_check_timestamp=report.first_target_check_at,
            fill_to_first_check_seconds=report.fill_to_first_target_check_seconds,
            entry_snapshot_to_first_check_seconds=report.entry_snapshot_to_first_check_seconds,
            max_favorable_excursion=metrics.max_favorable_excursion if metrics else None,
            max_adverse_excursion=metrics.max_adverse_excursion if metrics else None,
            net_profit=float(report.cycle.get("net_profit") or 0.0),
        )

    def _load_real_cycles(self, profile: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, strategy_profile, symbol, direction, status,
                       open_price, close_price, quantity, stake_usdt, gross_profit,
                       net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
                FROM real_pilot_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'HALTED')
                ORDER BY id ASC
                """,
                (profile,),
            ).fetchall()
        keys = [
            "id", "timestamp", "strategy_profile", "symbol", "direction", "status",
            "open_price", "close_price", "quantity", "stake_usdt", "gross_profit",
            "net_profit", "opened_at", "closed_at", "close_reason", "exchange_order_id", "run_id",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def _entry_order_times(self, cycle: dict[str, Any]) -> tuple[str | None, str | None]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, status
                FROM real_pilot_order_events
                WHERE strategy_profile = ?
                  AND run_id = ?
                ORDER BY id ASC
                """,
                (cycle["strategy_profile"], cycle["run_id"]),
            ).fetchall()
        sent = next((str(row[0]) for row in rows if str(row[1]) == "ATTEMPTED"), None)
        filled = next((str(row[0]) for row in rows if str(row[1]) == "FILLED"), None)
        return sent, filled

    def _close_order_times(self, cycle: dict[str, Any], *, close_reason: str) -> tuple[str | None, str | None]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, status, request_payload
                FROM real_pilot_order_events
                WHERE strategy_profile = ?
                ORDER BY id ASC
                """,
                (cycle["strategy_profile"],),
            ).fetchall()
        sent = None
        filled = None
        for row in rows:
            request = _json(row[2])
            if int(request.get("close_cycle_id", -1)) != int(cycle["id"]):
                continue
            if request.get("close_reason") != close_reason:
                continue
            if str(row[1]).startswith("ATTEMPTED"):
                sent = str(row[0])
            if str(row[1]) == "FILLED":
                filled = str(row[0])
        return sent, filled

    @staticmethod
    def _close_watcher_started_at(
        snapshots: list[dict[str, Any]],
        first_check: HFRealCloseWatcherTargetCheck | None,
    ) -> str | None:
        for row in snapshots:
            raw = _json(row.get("raw_payload_json"))
            if raw.get("close_watcher_started_at"):
                return str(raw["close_watcher_started_at"])
        return first_check.timestamp if first_check else None

    @staticmethod
    def _timeline(
        *,
        entry_sent: str | None,
        entry_filled: str | None,
        cycle: dict[str, Any],
        target_price: float,
        first_blackbox: dict[str, Any] | None,
        executable_touch: HFRealCloseWatcherTargetCheck | None,
        close_started: str | None,
        first_check: HFRealCloseWatcherTargetCheck | None,
        timeout_sent: str | None,
        timeout_filled: str | None,
    ) -> list[HFRealCloseWatcherTimelineEvent]:
        events = [
            ("entry_order_sent", entry_sent, "entry order ATTEMPTED event"),
            ("entry_order_filled", entry_filled, "entry order FILLED event"),
            ("real_cycle_created", str(cycle.get("opened_at") or cycle.get("timestamp") or ""), f"db_id={cycle['id']}"),
            ("target_price_fixed", str(cycle.get("opened_at") or cycle.get("timestamp") or ""), f"target={target_price:.8f}"),
            ("first_blackbox_snapshot", str(first_blackbox.get("timestamp")) if first_blackbox else None, f"phase={first_blackbox.get('phase')}" if first_blackbox else "N/A"),
            ("first_executable_target_touch", executable_touch.timestamp if executable_touch else None, f"price={executable_touch.executable_price:.8f}" if executable_touch and executable_touch.executable_price is not None else "N/A"),
            ("close_watcher_started", close_started, "inferred from first close watcher snapshot unless instrumented"),
            ("first_target_check", first_check.timestamp if first_check else None, f"condition={first_check.condition_met}" if first_check else "N/A"),
            ("timeout_order_sent", timeout_sent, "timeout close ATTEMPTED_CLOSE event"),
            ("timeout_order_filled", timeout_filled, "timeout close FILLED event"),
        ]
        timeline = [
            HFRealCloseWatcherTimelineEvent(name, timestamp, _seconds_between(entry_filled, timestamp), details)
            for name, timestamp, details in events
        ]
        return sorted(
            timeline,
            key=lambda event: (
                normalize_diagnostic_datetime(event.timestamp) is None,
                normalize_diagnostic_datetime(event.timestamp) or datetime.max.replace(tzinfo=timezone.utc),
            ),
        )

    @staticmethod
    def _recommendation(missed: int, touch_count: int, delays: list[float]) -> str:
        if not touch_count:
            return "NO_EXECUTABLE_TOUCHES_FOUND"
        if missed:
            return "BLIND_WINDOW_REQUIRES_REVIEW"
        if delays and max(delays) > 2.0:
            return "WATCHER_DELAY_OBSERVED"
        return "NO_MISSED_EXECUTABLE_TOUCHES"


def _seconds_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    start_dt = normalize_diagnostic_datetime(start)
    end_dt = normalize_diagnostic_datetime(end)
    if start_dt is None or end_dt is None:
        return None
    return max(0.0, (end_dt - start_dt).total_seconds())


def normalize_diagnostic_datetime(value: datetime | str | None) -> datetime | None:
    """Return a timezone-aware UTC datetime for mixed historical diagnostics timestamps.

    The existing SQLite history contains many ISO timestamps written by
    datetime.utcnow().isoformat(), so they are offset-naive but semantically UTC.
    Newer instrumentation may include +00:00 or other explicit offsets. Treat
    naive values as UTC explicitly instead of using the machine local timezone.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value)
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return normalize_diagnostic_datetime(value)
    except (TypeError, ValueError):
        return None


def _json(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
