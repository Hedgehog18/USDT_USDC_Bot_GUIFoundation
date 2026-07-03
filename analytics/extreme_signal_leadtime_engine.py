from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median

from analytics.extreme_market_discovery_engine import ExtremeMarketEvent
from analytics.extreme_signal_discovery_engine import (
    EXTREME_CONTROL_EXCLUSION_SECONDS,
    ExtremeSignalDiscoveryEngine,
    ExtremeSignalWindowMetrics,
)
from storage.database_manager import DatabaseManager


LEAD_TIMES_SECONDS = (5, 10, 15, 30, 45, 60, 90, 120, 180)
LEADTIME_WINDOW_SECONDS = 30
SIGNIFICANCE_THRESHOLD = 0.50


@dataclass(frozen=True)
class ExtremeSignalLeadTimeResult:
    signal_name: str
    lead_time_seconds: int
    events_detected: int
    detection_rate: float
    false_positives: int
    precision: float
    recall: float
    signal_strength: float


@dataclass(frozen=True)
class ExtremeSignalLeadTimeSummary:
    signal_name: str
    average_lead_time_seconds: float | None
    median_lead_time_seconds: float | None
    best_lead_time_seconds: int | None
    worst_lead_time_seconds: int | None
    detection_rate: float
    false_positive_rate: float
    first_significant_lead_time_seconds: int | None
    last_not_visible_lead_time_seconds: int | None
    signal_score: float
    recommendation: str


@dataclass(frozen=True)
class ExtremeSignalLeadTimeReport:
    profile: str
    extreme_events_analyzed: int
    control_windows_analyzed: int
    lead_time_results: list[ExtremeSignalLeadTimeResult]
    signal_summaries: list[ExtremeSignalLeadTimeSummary]
    best_signal: ExtremeSignalLeadTimeSummary | None
    final_recommendation: str
    report_path: str


class ExtremeSignalLeadTimeEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.signal_engine = ExtremeSignalDiscoveryEngine(database)

    def build_report(
        self,
        profile: str = "mean_reversion_hf_micro_v1",
        output_path: str | Path = "reports/extreme_signal_leadtime_report.txt",
    ) -> ExtremeSignalLeadTimeReport:
        discovery_report = self.signal_engine.discovery.build_report(profile)
        snapshots = self.signal_engine._load_hf_snapshots()
        control_windows = self.signal_engine._build_control_windows(discovery_report.events, snapshots)
        dominant_session = self._dominant_session(discovery_report.events)
        thresholds = self._thresholds(discovery_report.events, snapshots)
        results = self._lead_time_results(
            events=discovery_report.events,
            snapshots=snapshots,
            control_windows=control_windows,
            dominant_session=dominant_session,
            thresholds=thresholds,
        )
        summaries = self._summaries(results, len(discovery_report.events), len(control_windows))
        best = summaries[0] if summaries else None
        report = ExtremeSignalLeadTimeReport(
            profile=profile,
            extreme_events_analyzed=len(discovery_report.events),
            control_windows_analyzed=len(control_windows),
            lead_time_results=results,
            signal_summaries=summaries,
            best_signal=best,
            final_recommendation=self._final_recommendation(best, len(discovery_report.events)),
            report_path=str(output_path),
        )
        self._write_report(report, Path(output_path))
        return report

    def _lead_time_results(
        self,
        *,
        events: list[ExtremeMarketEvent],
        snapshots: list[dict],
        control_windows: list[ExtremeSignalWindowMetrics],
        dominant_session: str,
        thresholds: dict[str, float],
    ) -> list[ExtremeSignalLeadTimeResult]:
        predicates = self._predicates(dominant_session, thresholds)
        controls_by_lead = {
            lead: self._control_sample_for_lead(control_windows, lead)
            for lead in LEAD_TIMES_SECONDS
        }
        results: list[ExtremeSignalLeadTimeResult] = []
        for lead_time in LEAD_TIMES_SECONDS:
            event_metrics = [
                metric for event in events
                if (metric := self._event_metric_at_lead(event, snapshots, lead_time)) is not None
            ]
            controls = controls_by_lead[lead_time]
            for signal_name, predicate in predicates.items():
                detected = sum(1 for metric in event_metrics if predicate(metric))
                false_positives = sum(1 for metric in controls if predicate(metric))
                precision = detected / (detected + false_positives) if detected + false_positives else 0.0
                recall = detected / len(events) if events else 0.0
                detection_rate = detected / len(events) if events else 0.0
                false_positive_rate = false_positives / len(controls) if controls else 0.0
                strength = max(0.0, round((precision * 0.45) + (recall * 0.45) - (false_positive_rate * 0.25), 4))
                results.append(ExtremeSignalLeadTimeResult(
                    signal_name=signal_name,
                    lead_time_seconds=lead_time,
                    events_detected=detected,
                    detection_rate=detection_rate,
                    false_positives=false_positives,
                    precision=precision,
                    recall=recall,
                    signal_strength=strength,
                ))
        return results

    def _event_metric_at_lead(
        self,
        event: ExtremeMarketEvent,
        snapshots: list[dict],
        lead_time: int,
    ) -> ExtremeSignalWindowMetrics | None:
        event_time = self.signal_engine._parse_datetime(event.end_timestamp)
        if event_time is None:
            return None
        anchor = self.signal_engine._nearest_snapshot_time_before(snapshots, event_time) or event_time
        end_time = anchor - timedelta(seconds=lead_time)
        metric = self.signal_engine._window_metrics(
            snapshots=snapshots,
            end_time=end_time,
            window_seconds=LEADTIME_WINDOW_SECONDS,
            event_id=event.db_id,
        )
        if metric is not None:
            return metric
        # Entry diagnostics are point-in-time and can only approximate the closest lead.
        if lead_time <= 5:
            return self.signal_engine._fallback_event_metrics(event, lead_time)
        return None

    def _control_sample_for_lead(
        self,
        control_windows: list[ExtremeSignalWindowMetrics],
        lead_time: int,
    ) -> list[ExtremeSignalWindowMetrics]:
        window = min(max(lead_time, 5), 120)
        rows = [item for item in control_windows if item.window_seconds == window]
        if rows:
            return rows
        return control_windows

    def _summaries(
        self,
        results: list[ExtremeSignalLeadTimeResult],
        events_count: int,
        control_count: int,
    ) -> list[ExtremeSignalLeadTimeSummary]:
        signal_names = sorted({result.signal_name for result in results})
        summaries = [
            self._summary_for_signal(signal_name, results, events_count, control_count)
            for signal_name in signal_names
        ]
        return sorted(summaries, key=lambda item: item.signal_score, reverse=True)

    def _summary_for_signal(
        self,
        signal_name: str,
        results: list[ExtremeSignalLeadTimeResult],
        events_count: int,
        control_count: int,
    ) -> ExtremeSignalLeadTimeSummary:
        rows = [result for result in results if result.signal_name == signal_name]
        visible = [row.lead_time_seconds for row in rows if row.detection_rate > 0]
        significant = [
            row.lead_time_seconds
            for row in rows
            if row.detection_rate >= SIGNIFICANCE_THRESHOLD and row.precision >= 0.20
        ]
        not_visible = [row.lead_time_seconds for row in rows if row.detection_rate == 0]
        best_row = max(rows, key=lambda row: row.signal_strength) if rows else None
        detection_rate = best_row.detection_rate if best_row else 0.0
        false_positive_rate = (
            best_row.false_positives / control_count
            if best_row and control_count > 0
            else 0.0
        )
        score = self._signal_score(best_row, events_count)
        return ExtremeSignalLeadTimeSummary(
            signal_name=signal_name,
            average_lead_time_seconds=mean(visible) if visible else None,
            median_lead_time_seconds=median(visible) if visible else None,
            best_lead_time_seconds=max(visible) if visible else None,
            worst_lead_time_seconds=min(visible) if visible else None,
            detection_rate=detection_rate,
            false_positive_rate=false_positive_rate,
            first_significant_lead_time_seconds=max(significant) if significant else None,
            last_not_visible_lead_time_seconds=max(not_visible) if not_visible else None,
            signal_score=score,
            recommendation=self._signal_recommendation(events_count, score, detection_rate),
        )

    def _signal_score(self, best_row: ExtremeSignalLeadTimeResult | None, events_count: int) -> float:
        if best_row is None or events_count == 0:
            return 0.0
        sample_score = min(events_count / 30.0, 1.0) * 20.0
        precision_score = best_row.precision * 35.0
        recall_score = best_row.recall * 35.0
        lead_score = min(best_row.lead_time_seconds / 60.0, 1.0) * 10.0
        return round(sample_score + precision_score + recall_score + lead_score, 2)

    def _signal_recommendation(self, events_count: int, score: float, detection_rate: float) -> str:
        if events_count < 10:
            return "NEED_MORE_SIGNAL_DATA"
        if score >= 65 and detection_rate >= 0.50:
            return "READY_FOR_EXTREME_PAPER"
        if score >= 40 and detection_rate >= 0.35:
            return "NEED_MORE_SIGNAL_DATA"
        return "SIGNAL_TOO_LATE"

    def _final_recommendation(
        self,
        best: ExtremeSignalLeadTimeSummary | None,
        events_count: int,
    ) -> str:
        if events_count < 10 or best is None:
            return "NEED_MORE_SIGNAL_DATA"
        if best.recommendation == "READY_FOR_EXTREME_PAPER":
            return "READY_FOR_EXTREME_PAPER"
        if best.signal_score >= 40:
            return "NEED_MORE_SIGNAL_DATA"
        return "SIGNAL_TOO_LATE"

    def _thresholds(self, events: list[ExtremeMarketEvent], snapshots: list[dict]) -> dict[str, float]:
        metrics = [
            metric for event in events
            if (metric := self._event_metric_at_lead(event, snapshots, 5)) is not None
        ]
        velocity = self._median_abs([metric.price_velocity for metric in metrics])
        acceleration = self._median_abs([metric.price_acceleration for metric in metrics])
        distance = self._median_abs([metric.distance_from_short_center for metric in metrics])
        return {
            "velocity": max(velocity, 0.000001),
            "acceleration": max(acceleration, 0.000001),
            "distance": max(distance, 0.000001),
        }

    def _predicates(self, dominant_session: str, thresholds: dict[str, float]):
        return {
            "session_specific_signal": lambda item: item.session == dominant_session,
            "velocity_spike_before_extreme": (
                lambda item: abs(item.price_velocity or 0.0) >= thresholds["velocity"]
            ),
            "compression_before_extreme": lambda item: (item.compression_score or 0.0) >= 60.0,
            "flat_then_break": (
                lambda item: item.market_compressed
                and abs(item.price_velocity or 0.0) >= thresholds["velocity"]
            ),
            "acceleration_before_extreme": (
                lambda item: abs(item.price_acceleration or 0.0) >= thresholds["acceleration"]
            ),
            "short_center_distance_signal": (
                lambda item: abs(item.distance_from_short_center or 0.0) >= thresholds["distance"]
            ),
        }

    def _dominant_session(self, events: list[ExtremeMarketEvent]) -> str:
        if not events:
            return "UNKNOWN"
        return Counter(event.session for event in events).most_common(1)[0][0]

    def _median_abs(self, values: list[float | None]) -> float:
        cleaned = [abs(float(value)) for value in values if value is not None]
        return median(cleaned) if cleaned else 0.0

    def _write_report(self, report: ExtremeSignalLeadTimeReport, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "=== Extreme Signal Lead Time Report ===",
            f"Profile: {report.profile}",
            f"Extreme events analyzed: {report.extreme_events_analyzed}",
            f"Control windows analyzed: {report.control_windows_analyzed}",
            f"Best signal: {report.best_signal.signal_name if report.best_signal else 'N/A'}",
            f"Final recommendation: {report.final_recommendation}",
            "",
            "Lead time matrix:",
        ]
        for row in report.lead_time_results:
            lines.append(
                f"- {row.signal_name} @ {row.lead_time_seconds}s: "
                f"detected={row.events_detected} "
                f"detection_rate={row.detection_rate * 100:.2f}% "
                f"false_positives={row.false_positives} "
                f"precision={row.precision * 100:.2f}% "
                f"recall={row.recall * 100:.2f}% "
                f"strength={row.signal_strength:.4f}"
            )
        lines.append("")
        lines.append("Signal ranking:")
        for summary in report.signal_summaries:
            lines.append(
                f"- {summary.signal_name}: "
                f"avg_lead={self._fmt_seconds(summary.average_lead_time_seconds)} "
                f"median_lead={self._fmt_seconds(summary.median_lead_time_seconds)} "
                f"best_lead={self._fmt_seconds(summary.best_lead_time_seconds)} "
                f"worst_lead={self._fmt_seconds(summary.worst_lead_time_seconds)} "
                f"detection={summary.detection_rate * 100:.2f}% "
                f"false_positive={summary.false_positive_rate * 100:.2f}% "
                f"first_significant={self._fmt_seconds(summary.first_significant_lead_time_seconds)} "
                f"last_not_visible={self._fmt_seconds(summary.last_not_visible_lead_time_seconds)} "
                f"score={summary.signal_score:.2f} "
                f"recommendation={summary.recommendation}"
            )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _fmt_seconds(self, value: float | int | None) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.0f}s"
