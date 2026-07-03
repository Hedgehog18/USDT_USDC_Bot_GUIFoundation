from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median

from analytics.extreme_market_discovery_engine import ExtremeMarketDiscoveryEngine, ExtremeMarketEvent
from storage.database_manager import DatabaseManager


PRE_EVENT_WINDOWS_SECONDS = (5, 15, 30, 60, 120)
EXTREME_CONTROL_EXCLUSION_SECONDS = 180
CONTROL_MULTIPLIER = 3
EPSILON = 1e-12


@dataclass(frozen=True)
class ExtremeSignalWindowMetrics:
    event_id: int | None
    window_seconds: int
    timestamp: str
    price_velocity: float | None
    price_acceleration: float | None
    short_term_drift: float | None
    price_range: float | None
    compression_score: float | None
    flat_samples_count: int | None
    price_buffer_unique_values: int | None
    distance_from_short_center: float | None
    spread: float | None
    session: str
    hour: int | None
    previous_flat_duration_seconds: float | None
    market_compressed: bool


@dataclass(frozen=True)
class ExtremeSignalWindowComparison:
    window_seconds: int
    extreme_count: int
    control_count: int
    extreme_average: dict[str, float | None]
    extreme_median: dict[str, float | None]
    control_average: dict[str, float | None]
    control_median: dict[str, float | None]
    ratio_extreme_control: dict[str, float | None]
    signal_strength: dict[str, float]
    strongest_metric: str | None
    false_positive_risk: float


@dataclass(frozen=True)
class ExtremeSignalCandidate:
    name: str
    window_seconds: int
    extreme_events_covered: int
    control_windows_matched: int
    precision_estimate: float
    recall_estimate: float
    false_positive_count: int
    signal_score: float
    recommendation: str


@dataclass(frozen=True)
class ExtremeSignalDiscoveryReport:
    profile: str
    extreme_events_analyzed: int
    control_windows_analyzed: int
    best_pre_event_window: int | None
    strongest_signal_candidate: ExtremeSignalCandidate | None
    window_comparisons: list[ExtremeSignalWindowComparison]
    signal_candidates: list[ExtremeSignalCandidate]
    conclusion: str
    recommendation: str
    report_path: str


class ExtremeSignalDiscoveryEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.discovery = ExtremeMarketDiscoveryEngine(database)

    def build_report(
        self,
        profile: str = "mean_reversion_hf_micro_v1",
        output_path: str | Path = "reports/extreme_signal_discovery_report.txt",
    ) -> ExtremeSignalDiscoveryReport:
        discovery_report = self.discovery.build_report(profile)
        snapshots = self._load_hf_snapshots()
        extreme_windows = self._build_pre_event_windows(discovery_report.events, snapshots)
        control_windows = self._build_control_windows(discovery_report.events, snapshots)
        comparisons = [
            self._compare_window(window, extreme_windows, control_windows)
            for window in PRE_EVENT_WINDOWS_SECONDS
        ]
        candidates = self._signal_candidates(extreme_windows, control_windows, comparisons)
        best_window = self._best_window(comparisons)
        strongest = candidates[0] if candidates else None
        report = ExtremeSignalDiscoveryReport(
            profile=profile,
            extreme_events_analyzed=len(discovery_report.events),
            control_windows_analyzed=len(control_windows),
            best_pre_event_window=best_window,
            strongest_signal_candidate=strongest,
            window_comparisons=comparisons,
            signal_candidates=candidates,
            conclusion=self._conclusion(strongest, comparisons),
            recommendation=self._recommendation(strongest, len(discovery_report.events), len(control_windows)),
            report_path=str(output_path),
        )
        self._write_report(report, Path(output_path))
        return report

    def _build_pre_event_windows(
        self,
        events: list[ExtremeMarketEvent],
        snapshots: list[dict],
    ) -> list[ExtremeSignalWindowMetrics]:
        rows: list[ExtremeSignalWindowMetrics] = []
        for event in events:
            event_time = self._parse_datetime(event.end_timestamp)
            if event_time is None:
                continue
            pre_event_time = self._nearest_snapshot_time_before(snapshots, event_time) or (
                event_time - timedelta(microseconds=1)
            )
            for window in PRE_EVENT_WINDOWS_SECONDS:
                metrics = self._window_metrics(
                    snapshots=snapshots,
                    end_time=pre_event_time,
                    window_seconds=window,
                    event_id=event.db_id,
                )
                if metrics is None:
                    metrics = self._fallback_event_metrics(event, window)
                if metrics is not None:
                    rows.append(metrics)
        return rows

    def _build_control_windows(
        self,
        events: list[ExtremeMarketEvent],
        snapshots: list[dict],
    ) -> list[ExtremeSignalWindowMetrics]:
        event_times = [
            parsed for event in events
            if (parsed := self._parse_datetime(event.end_timestamp)) is not None
        ]
        rows: list[ExtremeSignalWindowMetrics] = []
        target_per_window = max(len(event_times) * CONTROL_MULTIPLIER, 1)
        selected_by_window: Counter[int] = Counter()
        for snapshot in snapshots:
            timestamp = self._parse_datetime(snapshot.get("timestamp"))
            if timestamp is None or self._near_extreme(timestamp, event_times):
                continue
            for window in PRE_EVENT_WINDOWS_SECONDS:
                if selected_by_window[window] >= target_per_window:
                    continue
                metrics = self._window_metrics(
                    snapshots=snapshots,
                    end_time=timestamp,
                    window_seconds=window,
                    event_id=None,
                )
                if metrics is not None:
                    rows.append(metrics)
                    selected_by_window[window] += 1
        return rows

    def _window_metrics(
        self,
        *,
        snapshots: list[dict],
        end_time: datetime,
        window_seconds: int,
        event_id: int | None,
    ) -> ExtremeSignalWindowMetrics | None:
        start_time = end_time - timedelta(seconds=window_seconds)
        window = [
            snapshot for snapshot in snapshots
            if (timestamp := self._parse_datetime(snapshot.get("timestamp"))) is not None
            and start_time <= timestamp <= end_time
        ]
        if not window:
            return None
        first = window[0]
        last = window[-1]
        prices = [float(snapshot.get("price") or 0.0) for snapshot in window]
        timestamps = [self._parse_datetime(snapshot.get("timestamp")) for snapshot in window]
        duration = self._duration_seconds(timestamps)
        price_velocity = ((prices[-1] - prices[0]) / duration) if duration and duration > 0 else 0.0
        previous_velocity = self._previous_velocity(snapshots, start_time, window_seconds)
        acceleration = (
            price_velocity - previous_velocity
            if previous_velocity is not None and price_velocity is not None
            else None
        )
        price_range = max(prices) - min(prices) if prices else None
        unique_values = len({round(price, 8) for price in prices})
        flat_samples = self._trailing_flat_samples(prices)
        spread = self._optional_float(last.get("spread"))
        distance = self._optional_float(last.get("distance_to_short_center"))
        compression = self._compression_score(price_range, unique_values, len(prices), spread)
        hour = self._parse_datetime(last.get("timestamp")).hour if self._parse_datetime(last.get("timestamp")) else None
        return ExtremeSignalWindowMetrics(
            event_id=event_id,
            window_seconds=window_seconds,
            timestamp=str(last.get("timestamp")),
            price_velocity=price_velocity,
            price_acceleration=acceleration,
            short_term_drift=prices[-1] - prices[0],
            price_range=price_range,
            compression_score=compression,
            flat_samples_count=flat_samples,
            price_buffer_unique_values=unique_values,
            distance_from_short_center=distance,
            spread=spread,
            session=str(last.get("session") or "UNKNOWN"),
            hour=hour,
            previous_flat_duration_seconds=self._previous_flat_duration_seconds(window),
            market_compressed=self._is_compressed(compression, price_range),
        )

    def _compare_window(
        self,
        window_seconds: int,
        extreme_windows: list[ExtremeSignalWindowMetrics],
        control_windows: list[ExtremeSignalWindowMetrics],
    ) -> ExtremeSignalWindowComparison:
        extreme = [item for item in extreme_windows if item.window_seconds == window_seconds]
        control = [item for item in control_windows if item.window_seconds == window_seconds]
        extreme_avg = self._aggregate(extreme, mean)
        control_avg = self._aggregate(control, mean)
        extreme_median = self._aggregate(extreme, median)
        control_median = self._aggregate(control, median)
        ratios = {
            metric: self._ratio(extreme_avg.get(metric), control_avg.get(metric))
            for metric in self._metric_names()
        }
        strengths = {
            metric: self._strength(extreme_avg.get(metric), control_avg.get(metric))
            for metric in self._metric_names()
        }
        strongest_metric = max(strengths, key=strengths.get) if strengths else None
        compressed_extreme = sum(1 for item in extreme if item.market_compressed)
        compressed_control = sum(1 for item in control if item.market_compressed)
        false_positive_risk = (compressed_control / len(control)) if control else 0.0
        if extreme and compressed_extreme == 0:
            false_positive_risk = 1.0
        return ExtremeSignalWindowComparison(
            window_seconds=window_seconds,
            extreme_count=len(extreme),
            control_count=len(control),
            extreme_average=extreme_avg,
            extreme_median=extreme_median,
            control_average=control_avg,
            control_median=control_median,
            ratio_extreme_control=ratios,
            signal_strength=strengths,
            strongest_metric=strongest_metric,
            false_positive_risk=false_positive_risk,
        )

    def _signal_candidates(
        self,
        extreme_windows: list[ExtremeSignalWindowMetrics],
        control_windows: list[ExtremeSignalWindowMetrics],
        comparisons: list[ExtremeSignalWindowComparison],
    ) -> list[ExtremeSignalCandidate]:
        best_window = self._best_window(comparisons) or 30
        extreme = [item for item in extreme_windows if item.window_seconds == best_window]
        control = [item for item in control_windows if item.window_seconds == best_window]
        extreme_velocity_threshold = self._median_abs([item.price_velocity for item in extreme])
        extreme_acceleration_threshold = self._median_abs([item.price_acceleration for item in extreme])
        distance_threshold = self._median_abs([item.distance_from_short_center for item in extreme])
        definitions = [
            (
                "compression_before_extreme",
                lambda item: (item.compression_score or 0.0) >= 60.0,
            ),
            (
                "velocity_spike_before_extreme",
                lambda item: abs(item.price_velocity or 0.0) >= max(extreme_velocity_threshold, 0.000001),
            ),
            (
                "acceleration_before_extreme",
                lambda item: abs(item.price_acceleration or 0.0) >= max(extreme_acceleration_threshold, 0.000001),
            ),
            (
                "flat_then_break",
                lambda item: item.market_compressed and abs(item.price_velocity or 0.0) >= max(extreme_velocity_threshold, 0.000001),
            ),
            (
                "session_specific_signal",
                lambda item: item.session == self._dominant_session(extreme),
            ),
            (
                "short_center_distance_signal",
                lambda item: abs(item.distance_from_short_center or 0.0) >= max(distance_threshold, 0.000001),
            ),
        ]
        candidates = [
            self._candidate_result(name, best_window, extreme, control, predicate)
            for name, predicate in definitions
        ]
        return sorted(candidates, key=lambda item: item.signal_score, reverse=True)

    def _candidate_result(
        self,
        name: str,
        window_seconds: int,
        extreme: list[ExtremeSignalWindowMetrics],
        control: list[ExtremeSignalWindowMetrics],
        predicate,
    ) -> ExtremeSignalCandidate:
        covered = sum(1 for item in extreme if predicate(item))
        false_positive = sum(1 for item in control if predicate(item))
        precision = covered / (covered + false_positive) if covered + false_positive else 0.0
        recall = covered / len(extreme) if extreme else 0.0
        false_positive_rate = false_positive / len(control) if control else 0.0
        score = max(0.0, round((precision * 45.0) + (recall * 45.0) - (false_positive_rate * 25.0), 2))
        return ExtremeSignalCandidate(
            name=name,
            window_seconds=window_seconds,
            extreme_events_covered=covered,
            control_windows_matched=false_positive,
            precision_estimate=precision,
            recall_estimate=recall,
            false_positive_count=false_positive,
            signal_score=score,
            recommendation=self._candidate_recommendation(len(extreme), score, precision, recall),
        )

    def _fallback_event_metrics(
        self,
        event: ExtremeMarketEvent,
        window_seconds: int,
    ) -> ExtremeSignalWindowMetrics | None:
        if (
            event.pre_price_velocity is None
            and event.pre_short_term_drift is None
            and event.pre_flat_samples_count is None
            and event.pre_buffer_unique_values is None
            and event.pre_short_center_distance is None
        ):
            return None
        flat_samples = event.pre_flat_samples_count
        unique_values = event.pre_buffer_unique_values
        compression = self._compression_from_entry_context(flat_samples, unique_values)
        compressed = bool(
            (compression is not None and compression >= 60.0)
            or (flat_samples is not None and flat_samples >= 5)
            or (unique_values is not None and unique_values <= 2)
        )
        return ExtremeSignalWindowMetrics(
            event_id=event.db_id,
            window_seconds=window_seconds,
            timestamp=event.start_timestamp,
            price_velocity=event.pre_price_velocity,
            price_acceleration=None,
            short_term_drift=event.pre_short_term_drift,
            price_range=None,
            compression_score=compression,
            flat_samples_count=flat_samples,
            price_buffer_unique_values=unique_values,
            distance_from_short_center=event.pre_short_center_distance,
            spread=event.spread_before,
            session=event.session,
            hour=event.hour,
            previous_flat_duration_seconds=float(flat_samples or 0),
            market_compressed=compressed,
        )

    def _candidate_recommendation(self, extreme_count: int, score: float, precision: float, recall: float) -> str:
        if extreme_count < 10:
            return "NEEDS_MORE_DATA"
        if score >= 55 and precision >= 0.20 and recall >= 0.50:
            return "STRONG_SIGNAL_CANDIDATE"
        if score >= 35 and recall >= 0.35:
            return "PROMISING_SIGNAL"
        return "WEAK_SIGNAL"

    def _best_window(self, comparisons: list[ExtremeSignalWindowComparison]) -> int | None:
        viable = [item for item in comparisons if item.extreme_count and item.control_count]
        if not viable:
            return None
        return max(
            viable,
            key=lambda item: max(item.signal_strength.values()) if item.signal_strength else 0.0,
        ).window_seconds

    def _conclusion(
        self,
        strongest: ExtremeSignalCandidate | None,
        comparisons: list[ExtremeSignalWindowComparison],
    ) -> str:
        if strongest is None:
            return "No pre-event signal could be evaluated from available data."
        if strongest.recommendation == "STRONG_SIGNAL_CANDIDATE":
            return f"Strongest visible pre-event signal is {strongest.name}."
        if strongest.recommendation == "PROMISING_SIGNAL":
            return f"Pre-event signal is promising but needs replay validation: {strongest.name}."
        if not any(item.extreme_count and item.control_count for item in comparisons):
            return "Insufficient pre-event and control windows to compare signals."
        return "No stable pre-event signal is visible yet."

    def _recommendation(self, strongest: ExtremeSignalCandidate | None, extreme_count: int, control_count: int) -> str:
        if extreme_count < 10 or control_count < 10:
            return "NEED_MORE_DATA"
        if strongest and strongest.recommendation in {"STRONG_SIGNAL_CANDIDATE", "PROMISING_SIGNAL"}:
            return "READY_FOR_EXTREME_SIGNAL_REPLAY"
        return "NO_STABLE_PRE_SIGNAL"

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

    def _aggregate(self, rows: list[ExtremeSignalWindowMetrics], fn) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for metric in self._metric_names():
            values = [self._metric_value(item, metric) for item in rows]
            cleaned = [value for value in values if value is not None]
            result[metric] = fn(cleaned) if cleaned else None
        return result

    def _metric_names(self) -> tuple[str, ...]:
        return (
            "price_velocity",
            "price_acceleration",
            "short_term_drift",
            "price_range",
            "compression_score",
            "flat_samples_count",
            "price_buffer_unique_values",
            "distance_from_short_center",
            "spread",
            "previous_flat_duration_seconds",
        )

    def _metric_value(self, item: ExtremeSignalWindowMetrics, metric: str) -> float | None:
        value = getattr(item, metric)
        if value is None:
            return None
        return float(value)

    def _previous_velocity(
        self,
        snapshots: list[dict],
        start_time: datetime,
        window_seconds: int,
    ) -> float | None:
        previous_start = start_time - timedelta(seconds=window_seconds)
        previous = [
            snapshot for snapshot in snapshots
            if (timestamp := self._parse_datetime(snapshot.get("timestamp"))) is not None
            and previous_start <= timestamp <= start_time
        ]
        if len(previous) < 2:
            return None
        prices = [float(snapshot.get("price") or 0.0) for snapshot in previous]
        timestamps = [self._parse_datetime(snapshot.get("timestamp")) for snapshot in previous]
        duration = self._duration_seconds(timestamps)
        if duration is None or duration <= 0:
            return None
        return (prices[-1] - prices[0]) / duration

    def _compression_score(
        self,
        price_range: float | None,
        unique_values: int,
        samples_count: int,
        spread: float | None,
    ) -> float | None:
        if price_range is None or samples_count <= 0:
            return None
        unique_component = max(0.0, 1.0 - (unique_values / samples_count))
        range_reference = max((spread or 0.0) * 3.0, 0.00001)
        range_component = max(0.0, 1.0 - min(price_range / range_reference, 1.0))
        return round((unique_component * 55.0) + (range_component * 45.0), 2)

    def _compression_from_entry_context(
        self,
        flat_samples: int | None,
        unique_values: int | None,
    ) -> float | None:
        if flat_samples is None and unique_values is None:
            return None
        flat_component = min((flat_samples or 0) / 10.0, 1.0) * 60.0
        unique_component = max(0.0, 1.0 - min((unique_values or 1) / 10.0, 1.0)) * 40.0
        return round(flat_component + unique_component, 2)

    def _is_compressed(self, compression_score: float | None, price_range: float | None) -> bool:
        return bool((compression_score is not None and compression_score >= 60.0) or (price_range is not None and price_range <= 0.00001))

    def _trailing_flat_samples(self, prices: list[float]) -> int:
        if not prices:
            return 0
        last = round(prices[-1], 8)
        count = 0
        for price in reversed(prices):
            if round(price, 8) != last:
                break
            count += 1
        return count

    def _previous_flat_duration_seconds(self, window: list[dict]) -> float:
        if len(window) < 2:
            return 0.0
        prices = [float(snapshot.get("price") or 0.0) for snapshot in window]
        flat_count = self._trailing_flat_samples(prices)
        if flat_count < 2:
            return 0.0
        timestamps = [self._parse_datetime(snapshot.get("timestamp")) for snapshot in window[-flat_count:]]
        duration = self._duration_seconds(timestamps)
        return duration or 0.0

    def _duration_seconds(self, timestamps: list[datetime | None]) -> float | None:
        cleaned = [timestamp for timestamp in timestamps if timestamp is not None]
        if len(cleaned) < 2:
            return None
        return max(0.0, (cleaned[-1] - cleaned[0]).total_seconds())

    def _median_abs(self, values: list[float | None]) -> float:
        cleaned = [abs(float(value)) for value in values if value is not None]
        return median(cleaned) if cleaned else 0.0

    def _dominant_session(self, rows: list[ExtremeSignalWindowMetrics]) -> str:
        if not rows:
            return "UNKNOWN"
        return Counter(row.session for row in rows).most_common(1)[0][0]

    def _near_extreme(self, timestamp: datetime, event_times: list[datetime]) -> bool:
        return any(abs((timestamp - event_time).total_seconds()) <= EXTREME_CONTROL_EXCLUSION_SECONDS for event_time in event_times)

    def _nearest_snapshot_time_before(self, snapshots: list[dict], target: datetime) -> datetime | None:
        candidates = [
            timestamp for snapshot in snapshots
            if (timestamp := self._parse_datetime(snapshot.get("timestamp"))) is not None
            and timestamp < target
        ]
        if not candidates:
            return None
        nearest = max(candidates)
        if (target - nearest).total_seconds() > 300:
            return None
        return nearest

    def _ratio(self, extreme: float | None, control: float | None) -> float | None:
        if extreme is None or control is None:
            return None
        denominator = abs(control) if abs(control) > EPSILON else EPSILON
        return extreme / denominator

    def _strength(self, extreme: float | None, control: float | None) -> float:
        if extreme is None or control is None:
            return 0.0
        return abs(extreme - control) / (abs(control) + EPSILON)

    def _optional_float(self, value: object) -> float | None:
        if value is None:
            return None
        return float(value)

    def _parse_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _write_report(self, report: ExtremeSignalDiscoveryReport, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "=== Extreme Signal Discovery Report ===",
            f"Profile: {report.profile}",
            f"Extreme events analyzed: {report.extreme_events_analyzed}",
            f"Control windows analyzed: {report.control_windows_analyzed}",
            f"Best pre-event window: {report.best_pre_event_window or 'N/A'}s",
            f"Strongest signal candidate: {report.strongest_signal_candidate.name if report.strongest_signal_candidate else 'N/A'}",
            f"Conclusion: {report.conclusion}",
            f"Recommendation: {report.recommendation}",
            "",
            "Pre-event window comparison:",
        ]
        for comparison in report.window_comparisons:
            lines.append(
                f"- {comparison.window_seconds}s: extreme={comparison.extreme_count} "
                f"control={comparison.control_count} strongest={comparison.strongest_metric or 'N/A'} "
                f"false_positive_risk={comparison.false_positive_risk * 100:.2f}%"
            )
            for metric in comparison.signal_strength:
                lines.append(
                    f"  - {metric}: extreme_avg={self._fmt(comparison.extreme_average.get(metric))} "
                    f"control_avg={self._fmt(comparison.control_average.get(metric))} "
                    f"ratio={self._fmt(comparison.ratio_extreme_control.get(metric))} "
                    f"strength={comparison.signal_strength.get(metric, 0.0):.2f}"
                )
        lines.append("")
        lines.append("Signal candidates ranking:")
        for candidate in report.signal_candidates:
            lines.append(
                f"- {candidate.name}: window={candidate.window_seconds}s "
                f"covered={candidate.extreme_events_covered} "
                f"control={candidate.control_windows_matched} "
                f"precision={candidate.precision_estimate * 100:.2f}% "
                f"recall={candidate.recall_estimate * 100:.2f}% "
                f"false_positive={candidate.false_positive_count} "
                f"score={candidate.signal_score:.2f} "
                f"recommendation={candidate.recommendation}"
            )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _fmt(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.8f}"
