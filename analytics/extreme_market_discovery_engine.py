from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median

from analytics.hf_extreme_price import is_extreme_close_price
from analytics.market_session_diagnostics_engine import MarketSessionDiagnosticsEngine
from storage.database_manager import DatabaseManager


RECOVERY_VELOCITY_THRESHOLD = 0.00002
CLUSTER_GAP_SECONDS = 600
MAX_SNAPSHOT_MATCH_SECONDS = 300


@dataclass(frozen=True)
class ExtremeMarketEvent:
    db_id: int
    start_timestamp: str
    end_timestamp: str
    duration_seconds: float | None
    session: str
    hour: int | None
    close_price: float
    maximum_short_center_distance: float | None
    price_velocity_before: float | None
    price_velocity_after: float | None
    acceleration: float | None
    spread_before: float | None
    spread_after: float | None
    recovery_seconds: float | None
    amplitude_class: str
    pre_price_velocity: float | None
    pre_short_term_drift: float | None
    pre_flat_samples_count: int | None
    pre_buffer_unique_values: int | None
    pre_short_center_distance: float | None


@dataclass(frozen=True)
class ExtremeMarketDiscoveryReport:
    profile: str
    events: list[ExtremeMarketEvent]
    count: int
    average_duration_seconds: float | None
    median_duration_seconds: float | None
    longest_duration_seconds: float | None
    shortest_duration_seconds: float | None
    average_recovery_seconds: float | None
    median_recovery_seconds: float | None
    by_amplitude: dict[str, int]
    by_session: dict[str, int]
    by_hour: dict[int, int]
    average_events_per_day: float
    maximum_events_per_day: int
    minimum_events_per_day: int
    cluster_distribution: dict[str, int]
    average_pre_price_velocity: float | None
    average_pre_short_term_drift: float | None
    average_pre_flat_samples_count: float | None
    average_pre_buffer_unique_values: float | None
    average_pre_short_center_distance: float | None
    conclusion: str
    recommendation: str


class ExtremeMarketDiscoveryEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, profile: str = "mean_reversion_hf_micro_v1") -> ExtremeMarketDiscoveryReport:
        cycles = self._load_extreme_cycles(profile)
        snapshots = self._load_hf_snapshots()
        events = [self._event(cycle, snapshots) for cycle in cycles]
        durations = [event.duration_seconds for event in events if event.duration_seconds is not None]
        recoveries = [event.recovery_seconds for event in events if event.recovery_seconds is not None]
        by_day = Counter(self._day_key(event.end_timestamp) for event in events if self._day_key(event.end_timestamp))
        cluster_distribution = self._cluster_distribution(events)
        return ExtremeMarketDiscoveryReport(
            profile=profile,
            events=events,
            count=len(events),
            average_duration_seconds=mean(durations) if durations else None,
            median_duration_seconds=median(durations) if durations else None,
            longest_duration_seconds=max(durations) if durations else None,
            shortest_duration_seconds=min(durations) if durations else None,
            average_recovery_seconds=mean(recoveries) if recoveries else None,
            median_recovery_seconds=median(recoveries) if recoveries else None,
            by_amplitude=dict(Counter(event.amplitude_class for event in events)),
            by_session=dict(Counter(event.session for event in events)),
            by_hour=dict(Counter(event.hour for event in events if event.hour is not None)),
            average_events_per_day=(len(events) / len(by_day)) if by_day else 0.0,
            maximum_events_per_day=max(by_day.values()) if by_day else 0,
            minimum_events_per_day=min(by_day.values()) if by_day else 0,
            cluster_distribution=cluster_distribution,
            average_pre_price_velocity=self._avg(event.pre_price_velocity for event in events),
            average_pre_short_term_drift=self._avg(event.pre_short_term_drift for event in events),
            average_pre_flat_samples_count=self._avg(event.pre_flat_samples_count for event in events),
            average_pre_buffer_unique_values=self._avg(event.pre_buffer_unique_values for event in events),
            average_pre_short_center_distance=self._avg(event.pre_short_center_distance for event in events),
            conclusion=self._conclusion(events),
            recommendation=self._recommendation(events),
        )

    def _load_extreme_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    pc.id, pc.opened_at, pc.closed_at, pc.timestamp,
                    pc.close_price, pc.open_price, pc.direction,
                    diag.current_price, diag.previous_price, diag.last_different_price,
                    diag.flat_samples_count, diag.price_buffer_unique_values,
                    diag.short_center
                FROM paper_cycles pc
                LEFT JOIN hf_paper_cycle_entry_diagnostics diag
                    ON diag.paper_cycle_id = pc.id
                WHERE pc.strategy_profile = ?
                  AND pc.status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY pc.closed_at ASC, pc.id ASC
                """,
                (profile,),
            ).fetchall()
        keys = (
            "id", "opened_at", "closed_at", "timestamp", "close_price", "open_price",
            "direction", "entry_current_price", "previous_price", "last_different_price",
            "flat_samples_count", "price_buffer_unique_values", "short_center",
        )
        return [
            dict(zip(keys, row))
            for row in rows
            if is_extreme_close_price(float(row[4] or 0.0))
        ]

    def _load_hf_snapshots(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp, price, spread, distance_to_short_center,
                    price_change_5_sec, price_change_10_sec, price_change_30_sec,
                    price_change_1_min, price_change_5_min, session
                FROM market_snapshots_hf
                ORDER BY timestamp ASC
                """
            ).fetchall()
        keys = (
            "timestamp", "price", "spread", "distance_to_short_center",
            "price_change_5_sec", "price_change_10_sec", "price_change_30_sec",
            "price_change_1_min", "price_change_5_min", "session",
        )
        return [dict(zip(keys, row)) for row in rows]

    def _event(self, cycle: dict, snapshots: list[dict]) -> ExtremeMarketEvent:
        start = self._parse_datetime(cycle.get("opened_at") or cycle.get("timestamp"))
        end = self._parse_datetime(cycle.get("closed_at") or cycle.get("timestamp"))
        before = self._nearest_snapshot(snapshots, end, direction="before")
        after = self._nearest_snapshot(snapshots, end, direction="after")
        window = self._snapshots_between(snapshots, start, end)
        max_distance = self._max_abs(snapshot.get("distance_to_short_center") for snapshot in window)
        if max_distance is None:
            max_distance = self._entry_short_center_distance(cycle)
        before_velocity = self._optional_float(before.get("price_change_5_sec")) if before else None
        after_velocity = self._optional_float(after.get("price_change_5_sec")) if after else None
        recovery_seconds = self._recovery_seconds(snapshots, end)
        hour = end.hour if end else None
        return ExtremeMarketEvent(
            db_id=int(cycle["id"]),
            start_timestamp=self._format_dt(start, cycle.get("opened_at") or cycle.get("timestamp")),
            end_timestamp=self._format_dt(end, cycle.get("closed_at") or cycle.get("timestamp")),
            duration_seconds=max(0.0, (end - start).total_seconds()) if start and end else None,
            session=(
                str(before.get("session"))
                if before and before.get("session")
                else MarketSessionDiagnosticsEngine.classify_session(hour or 0)
            ),
            hour=hour,
            close_price=float(cycle.get("close_price") or 0.0),
            maximum_short_center_distance=max_distance,
            price_velocity_before=before_velocity,
            price_velocity_after=after_velocity,
            acceleration=(after_velocity - before_velocity) if before_velocity is not None and after_velocity is not None else None,
            spread_before=self._optional_float(before.get("spread")) if before else None,
            spread_after=self._optional_float(after.get("spread")) if after else None,
            recovery_seconds=recovery_seconds,
            amplitude_class=self._amplitude_class(max_distance),
            pre_price_velocity=self._entry_velocity(cycle),
            pre_short_term_drift=self._entry_drift(cycle),
            pre_flat_samples_count=self._optional_int(cycle.get("flat_samples_count")),
            pre_buffer_unique_values=self._optional_int(cycle.get("price_buffer_unique_values")),
            pre_short_center_distance=self._entry_short_center_distance(cycle),
        )

    def _cluster_distribution(self, events: list[ExtremeMarketEvent]) -> dict[str, int]:
        groups: list[list[ExtremeMarketEvent]] = []
        current: list[ExtremeMarketEvent] = []
        previous_time: datetime | None = None
        for event in sorted(events, key=lambda item: item.end_timestamp):
            event_time = self._parse_datetime(event.end_timestamp)
            if not current or previous_time is None or event_time is None:
                current = [event]
                groups.append(current)
            elif (event_time - previous_time).total_seconds() <= CLUSTER_GAP_SECONDS:
                current.append(event)
            else:
                current = [event]
                groups.append(current)
            previous_time = event_time
        labels = Counter(self._cluster_label(len(group)) for group in groups)
        return dict(labels)

    def _cluster_label(self, size: int) -> str:
        if size <= 1:
            return "Single"
        if size == 2:
            return "Double"
        if size == 3:
            return "Triple"
        return "Cluster"

    def _conclusion(self, events: list[ExtremeMarketEvent]) -> str:
        if len(events) < 10:
            return "Insufficient data to identify a stable Extreme Market pattern."
        flat_values = [event.pre_flat_samples_count or 0 for event in events]
        velocities = [abs(event.pre_price_velocity or 0.0) for event in events]
        drifts = [abs(event.pre_short_term_drift or 0.0) for event in events]
        if flat_values and mean(flat_values) >= 5:
            return "Extreme events most often appear after flat/compressed market conditions."
        if velocities and mean(velocities) > RECOVERY_VELOCITY_THRESHOLD:
            return "Extreme events most often appear after a velocity spike."
        if drifts and mean(drifts) > RECOVERY_VELOCITY_THRESHOLD:
            return "Extreme events most often appear after short-term drift."
        return "Extreme event causes are mixed or not yet clear from available diagnostics."

    def _recommendation(self, events: list[ExtremeMarketEvent]) -> str:
        if len(events) >= 20:
            return "READY_FOR_EXTREME_REPLAY"
        return "NEED_MORE_EXTREME_DATA"

    def _recovery_seconds(self, snapshots: list[dict], end: datetime | None) -> float | None:
        if end is None:
            return None
        for snapshot in snapshots:
            timestamp = self._parse_datetime(snapshot.get("timestamp"))
            if timestamp is None or timestamp < end:
                continue
            velocity = abs(float(snapshot.get("price_change_5_sec") or 0.0))
            distance = abs(float(snapshot.get("distance_to_short_center") or 0.0))
            if velocity <= RECOVERY_VELOCITY_THRESHOLD and distance <= 0.00005:
                return max(0.0, (timestamp - end).total_seconds())
        return None

    def _nearest_snapshot(self, snapshots: list[dict], target: datetime | None, *, direction: str) -> dict | None:
        if target is None:
            return None
        matching = []
        for snapshot in snapshots:
            timestamp = self._parse_datetime(snapshot.get("timestamp"))
            if timestamp is None:
                continue
            if direction == "before" and timestamp <= target:
                matching.append((abs((target - timestamp).total_seconds()), snapshot))
            if direction == "after" and timestamp >= target:
                matching.append((abs((timestamp - target).total_seconds()), snapshot))
        if not matching:
            return None
        distance, snapshot = min(matching, key=lambda item: item[0])
        if distance > MAX_SNAPSHOT_MATCH_SECONDS:
            return None
        return snapshot

    def _snapshots_between(
        self,
        snapshots: list[dict],
        start: datetime | None,
        end: datetime | None,
    ) -> list[dict]:
        if start is None or end is None:
            return []
        return [
            snapshot for snapshot in snapshots
            if (timestamp := self._parse_datetime(snapshot.get("timestamp"))) is not None
            and start <= timestamp <= end
        ]

    def _entry_velocity(self, cycle: dict) -> float | None:
        current = self._optional_float(cycle.get("entry_current_price"))
        previous = self._optional_float(cycle.get("previous_price"))
        if current is None or previous is None:
            return None
        return current - previous

    def _entry_drift(self, cycle: dict) -> float | None:
        current = self._optional_float(cycle.get("entry_current_price"))
        last = self._optional_float(cycle.get("last_different_price"))
        if current is None or last is None:
            return None
        return current - last

    def _entry_short_center_distance(self, cycle: dict) -> float | None:
        current = self._optional_float(cycle.get("entry_current_price"))
        center = self._optional_float(cycle.get("short_center"))
        if current is None or center is None:
            return None
        return current - center

    def _amplitude_class(self, max_distance: float | None) -> str:
        if max_distance is None:
            return "UNKNOWN"
        value = abs(max_distance)
        if value < 0.00005:
            return "Micro Extreme"
        if value < 0.00020:
            return "Medium Extreme"
        return "Large Extreme"

    def _max_abs(self, values) -> float | None:
        cleaned = [abs(float(value)) for value in values if value is not None]
        return max(cleaned) if cleaned else None

    def _avg(self, values) -> float | None:
        cleaned = [float(value) for value in values if value is not None]
        return mean(cleaned) if cleaned else None

    def _day_key(self, timestamp: str) -> str | None:
        parsed = self._parse_datetime(timestamp)
        return parsed.date().isoformat() if parsed else None

    def _optional_float(self, value: object) -> float | None:
        if value is None:
            return None
        return float(value)

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def _parse_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _format_dt(self, parsed: datetime | None, fallback: object) -> str:
        if parsed is None:
            return str(fallback or "")
        return parsed.isoformat()
