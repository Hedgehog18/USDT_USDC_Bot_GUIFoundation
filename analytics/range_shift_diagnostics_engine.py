from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


RANGE_SHIFT_LOOKBACK = timedelta(hours=1)
RANGE_SHIFT_THRESHOLDS = (0.00005, 0.00010, 0.00020, 0.00050)


@dataclass(frozen=True)
class RangeShiftSnapshot:
    timestamp: datetime
    timestamp_text: str
    price: float
    work_center: float
    short_center: float
    long_center: float


@dataclass(frozen=True)
class OpenCycleRangeShift:
    db_id: int
    cycle_id: int
    direction: str
    opened_at: str
    open_price: float
    current_price: float
    target_price: float
    work_center_at_entry: float | None
    current_work_center: float | None
    short_center_at_entry: float | None
    current_short_center: float | None
    long_center_at_entry: float | None
    current_long_center: float | None
    center_shift_amount: float | None
    center_shift_percent: float | None
    center_shift_direction: str
    current_work_range_min: float | None
    current_work_range_max: float | None
    target_outside_current_work_range: bool
    open_price_no_longer_realistic_mean_reversion_target: bool


@dataclass(frozen=True)
class ClosedCycleRangeShiftSummary:
    closed_cycles_count: int
    average_center_shift_to_close: float | None
    successful_average_center_shift: float | None
    center_shift_distribution: list[tuple[str, int]]


@dataclass(frozen=True)
class RangeShiftThresholdSimulation:
    threshold_percent: float
    stale_open_cycles: int
    rebase_target_candidates: int
    stale_cycle_ids: list[int]


@dataclass(frozen=True)
class RangeShiftDiagnosticsReport:
    profile: str
    open_cycles: list[OpenCycleRangeShift]
    closed_summary: ClosedCycleRangeShiftSummary
    threshold_simulations: list[RangeShiftThresholdSimulation]


class RangeShiftDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(self, *, profile: str) -> RangeShiftDiagnosticsReport:
        snapshots = self._load_snapshots()
        latest_snapshot = snapshots[-1] if snapshots else None
        open_cycles = self._open_cycle_diagnostics(profile, snapshots, latest_snapshot)
        return RangeShiftDiagnosticsReport(
            profile=profile,
            open_cycles=open_cycles,
            closed_summary=self._closed_cycle_summary(profile, snapshots),
            threshold_simulations=[
                self._simulate_threshold(threshold, open_cycles)
                for threshold in RANGE_SHIFT_THRESHOLDS
            ],
        )

    def _open_cycle_diagnostics(
        self,
        profile: str,
        snapshots: list[RangeShiftSnapshot],
        latest_snapshot: RangeShiftSnapshot | None,
    ) -> list[OpenCycleRangeShift]:
        items: list[OpenCycleRangeShift] = []
        if latest_snapshot is None:
            return items

        range_min, range_max = self._observed_range(snapshots, latest_snapshot.timestamp)
        for row in self._load_cycle_rows(profile, status="OPEN"):
            (
                db_id,
                _timestamp,
                cycle_id,
                _strategy_profile,
                direction,
                _status,
                open_price,
                close_price,
                _quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                _net_profit,
                opened_at,
                _closed_at,
            ) = row
            opened_at_text = clean_display_text(opened_at)
            entry_snapshot = self._snapshot_at_or_before(snapshots, self._parse_timestamp(opened_at_text))
            center_shift = self._diff(
                latest_snapshot.work_center,
                entry_snapshot.work_center if entry_snapshot else None,
            )
            center_shift_percent = (
                abs(center_shift) / entry_snapshot.work_center
                if entry_snapshot and entry_snapshot.work_center
                else None
            )
            direction_text = clean_display_text(direction)
            target_price = float(close_price)
            current_center = latest_snapshot.work_center
            items.append(
                OpenCycleRangeShift(
                    db_id=int(db_id),
                    cycle_id=int(cycle_id),
                    direction=direction_text,
                    opened_at=opened_at_text,
                    open_price=float(open_price),
                    current_price=latest_snapshot.price,
                    target_price=target_price,
                    work_center_at_entry=entry_snapshot.work_center if entry_snapshot else None,
                    current_work_center=latest_snapshot.work_center,
                    short_center_at_entry=entry_snapshot.short_center if entry_snapshot else None,
                    current_short_center=latest_snapshot.short_center,
                    long_center_at_entry=entry_snapshot.long_center if entry_snapshot else None,
                    current_long_center=latest_snapshot.long_center,
                    center_shift_amount=center_shift,
                    center_shift_percent=center_shift_percent,
                    center_shift_direction=self._shift_direction(center_shift),
                    current_work_range_min=range_min,
                    current_work_range_max=range_max,
                    target_outside_current_work_range=self._outside_range(target_price, range_min, range_max),
                    open_price_no_longer_realistic_mean_reversion_target=(
                        self._target_no_longer_realistic(direction_text, target_price, current_center)
                    ),
                )
            )
        return items

    def _closed_cycle_summary(
        self,
        profile: str,
        snapshots: list[RangeShiftSnapshot],
    ) -> ClosedCycleRangeShiftSummary:
        shifts: list[float] = []
        successful_shifts: list[float] = []
        distribution: Counter[str] = Counter()
        for row in self._load_cycle_rows(profile, status="CLOSED"):
            (
                _db_id,
                _timestamp,
                _cycle_id,
                _strategy_profile,
                _direction,
                _status,
                _open_price,
                _close_price,
                _quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                net_profit,
                opened_at,
                closed_at,
            ) = row
            if not closed_at:
                continue
            entry_snapshot = self._snapshot_at_or_before(snapshots, self._parse_timestamp(clean_display_text(opened_at)))
            close_snapshot = self._snapshot_at_or_before(snapshots, self._parse_timestamp(clean_display_text(closed_at)))
            if entry_snapshot is None or close_snapshot is None:
                continue
            shift = close_snapshot.work_center - entry_snapshot.work_center
            shifts.append(shift)
            distribution[self._shift_bucket(shift, entry_snapshot.work_center)] += 1
            if float(net_profit) > 0:
                successful_shifts.append(shift)

        return ClosedCycleRangeShiftSummary(
            closed_cycles_count=len(shifts),
            average_center_shift_to_close=self._average(shifts),
            successful_average_center_shift=self._average(successful_shifts),
            center_shift_distribution=sorted(distribution.items(), key=lambda item: item[0]),
        )

    @staticmethod
    def _simulate_threshold(
        threshold: float,
        open_cycles: list[OpenCycleRangeShift],
    ) -> RangeShiftThresholdSimulation:
        stale = [
            item
            for item in open_cycles
            if item.center_shift_percent is not None and item.center_shift_percent > threshold
        ]
        rebase = [
            item
            for item in open_cycles
            if item.target_outside_current_work_range
            or item.open_price_no_longer_realistic_mean_reversion_target
        ]
        return RangeShiftThresholdSimulation(
            threshold_percent=threshold * 100.0,
            stale_open_cycles=len(stale),
            rebase_target_candidates=len(rebase),
            stale_cycle_ids=[item.db_id for item in stale],
        )

    def _load_cycle_rows(self, profile: str, *, status: str) -> list[tuple]:
        with self.database.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, open_fee, close_fee,
                       gross_profit, net_profit, opened_at, closed_at
                FROM paper_cycles
                WHERE strategy_profile = ? AND status = ?
                ORDER BY opened_at ASC
                """,
                (profile, status),
            ).fetchall()

    def _load_snapshots(self) -> list[RangeShiftSnapshot]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price, work_center, short_center, long_center
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            RangeShiftSnapshot(
                timestamp=self._parse_timestamp(timestamp),
                timestamp_text=clean_display_text(timestamp),
                price=float(price or 0.0),
                work_center=float(work_center or 0.0),
                short_center=float(short_center or 0.0),
                long_center=float(long_center or 0.0),
            )
            for timestamp, price, work_center, short_center, long_center in rows
        ]

    @staticmethod
    def _observed_range(
        snapshots: list[RangeShiftSnapshot],
        timestamp: datetime,
    ) -> tuple[float | None, float | None]:
        window = [
            snapshot.price
            for snapshot in snapshots
            if timestamp - RANGE_SHIFT_LOOKBACK <= snapshot.timestamp <= timestamp
        ]
        if not window:
            return None, None
        return min(window), max(window)

    @staticmethod
    def _target_no_longer_realistic(direction: str, target_price: float, current_work_center: float) -> bool:
        if direction == "BUY_USDC":
            return target_price > current_work_center
        if direction == "SELL_USDC":
            return target_price < current_work_center
        return False

    @staticmethod
    def _outside_range(value: float, range_min: float | None, range_max: float | None) -> bool:
        if range_min is None or range_max is None:
            return False
        return value < range_min or value > range_max

    @staticmethod
    def _diff(current: float | None, previous: float | None) -> float | None:
        if current is None or previous is None:
            return None
        return current - previous

    @staticmethod
    def _shift_direction(shift: float | None) -> str:
        if shift is None:
            return "UNKNOWN"
        if shift > 0:
            return "UP"
        if shift < 0:
            return "DOWN"
        return "FLAT"

    @staticmethod
    def _shift_bucket(shift: float, reference: float) -> str:
        if reference == 0:
            return "UNKNOWN"
        percent = abs(shift) / reference
        if percent <= 0.00005:
            return "<=0.005%"
        if percent <= 0.00010:
            return "<=0.01%"
        if percent <= 0.00020:
            return "<=0.02%"
        if percent <= 0.00050:
            return "<=0.05%"
        return ">0.05%"

    @staticmethod
    def _snapshot_at_or_before(
        snapshots: list[RangeShiftSnapshot],
        timestamp: datetime,
    ) -> RangeShiftSnapshot | None:
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        selected = None
        for snapshot in snapshots:
            if snapshot.timestamp <= timestamp:
                selected = snapshot
            else:
                break
        return selected

    @staticmethod
    def _parse_timestamp(value) -> datetime:
        parsed = datetime.fromisoformat(clean_display_text(value))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None
