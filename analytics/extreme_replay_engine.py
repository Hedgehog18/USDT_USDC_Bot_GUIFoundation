from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median

from analytics.extreme_market_discovery_engine import (
    CLUSTER_GAP_SECONDS,
    RECOVERY_VELOCITY_THRESHOLD,
    ExtremeMarketDiscoveryEngine,
    ExtremeMarketEvent,
)
from storage.database_manager import DatabaseManager


DELAYED_ENTRY_SECONDS = 30
FLAT_EXIT_DISTANCE_THRESHOLD = 0.00005


@dataclass(frozen=True)
class ExtremeReplayScenarioResult:
    scenario: str
    entered: bool
    entry_timestamp: str | None
    direction: str
    entry_price: float | None
    exit_price: float | None
    maximum_favorable_excursion: float | None
    maximum_adverse_excursion: float | None
    recovery_seconds: float | None
    holding_seconds: float | None
    distance_travelled: float | None
    potential_profit: float | None
    potential_loss: float | None
    reward_risk: float | None
    skipped_reason: str | None = None


@dataclass(frozen=True)
class ExtremeReplayEventResult:
    event_number: int
    db_id: int
    start_timestamp: str
    end_timestamp: str
    duration_seconds: float | None
    amplitude_class: str
    session: str
    cluster_label: str
    scenarios: list[ExtremeReplayScenarioResult]


@dataclass(frozen=True)
class ExtremeReplayStatistics:
    events_count: int
    scenario_count: int
    entered_replays_count: int
    average_potential_profit: float | None
    median_potential_profit: float | None
    average_adverse_excursion: float | None
    average_favorable_excursion: float | None
    average_reward_risk: float | None
    reward_risk_distribution: dict[str, int]
    assessment: str


@dataclass(frozen=True)
class ExtremeReplayReport:
    profile: str
    events: list[ExtremeReplayEventResult]
    statistics: ExtremeReplayStatistics
    report_path: str


class ExtremeReplayEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.discovery = ExtremeMarketDiscoveryEngine(database)

    def build_report(
        self,
        profile: str = "mean_reversion_hf_micro_v1",
        output_path: str | Path = "reports/extreme_replay_report.txt",
    ) -> ExtremeReplayReport:
        discovery_report = self.discovery.build_report(profile)
        snapshots = self.discovery._load_hf_snapshots()
        cycle_context = {int(item["id"]): item for item in self.discovery._load_extreme_cycles(profile)}
        cluster_labels = self._cluster_labels(discovery_report.events)
        event_results = [
            self._replay_event(
                event_number=index,
                event=event,
                snapshots=snapshots,
                cycle_context=cycle_context.get(event.db_id, {}),
                cluster_label=cluster_labels.get(event.db_id, "Single"),
            )
            for index, event in enumerate(discovery_report.events, start=1)
        ]
        report = ExtremeReplayReport(
            profile=profile,
            events=event_results,
            statistics=self._statistics(event_results),
            report_path=str(output_path),
        )
        self._write_report(report, Path(output_path))
        return report

    def _replay_event(
        self,
        *,
        event_number: int,
        event: ExtremeMarketEvent,
        snapshots: list[dict],
        cycle_context: dict,
        cluster_label: str,
    ) -> ExtremeReplayEventResult:
        start = self._parse_datetime(event.start_timestamp)
        end = self._parse_datetime(event.end_timestamp)
        scenario_specs = [
            ("Immediate Entry", start),
            ("Entry after 30s", (start + timedelta(seconds=DELAYED_ENTRY_SECONDS)) if start else None),
            ("Entry after velocity spike", self._velocity_spike_timestamp(snapshots, start, end)),
            ("Entry after flat exit", self._flat_exit_timestamp(snapshots, start, end)),
        ]
        return ExtremeReplayEventResult(
            event_number=event_number,
            db_id=event.db_id,
            start_timestamp=event.start_timestamp,
            end_timestamp=event.end_timestamp,
            duration_seconds=event.duration_seconds,
            amplitude_class=event.amplitude_class,
            session=event.session,
            cluster_label=cluster_label,
            scenarios=[
                self._scenario_result(
                    name=name,
                    entry_time=entry_time,
                    event=event,
                    snapshots=snapshots,
                    cycle_context=cycle_context,
                    end=end,
                )
                for name, entry_time in scenario_specs
            ],
        )

    def _scenario_result(
        self,
        *,
        name: str,
        entry_time: datetime | None,
        event: ExtremeMarketEvent,
        snapshots: list[dict],
        cycle_context: dict,
        end: datetime | None,
    ) -> ExtremeReplayScenarioResult:
        if entry_time is None or end is None:
            return self._skipped(name, "missing timestamp")
        if entry_time > end:
            return self._skipped(name, "entry after event end")
        entry_snapshot = self._nearest_snapshot_at_or_after(snapshots, entry_time, end)
        entry_price = self._optional_float(entry_snapshot.get("price")) if entry_snapshot else None
        if entry_price is None and name == "Immediate Entry":
            entry_price = self._optional_float(cycle_context.get("open_price"))
        if entry_price is None:
            return self._skipped(name, "missing entry price")
        exit_price = event.close_price
        if exit_price == entry_price:
            return self._skipped(name, "flat event price")
        direction = "SELL_USDC" if exit_price < entry_price else "BUY_USDC"
        prices = self._future_prices(snapshots, entry_time, end, entry_price, exit_price)
        favorable, adverse = self._excursions(direction, entry_price, prices)
        potential_loss = adverse
        reward_risk = (favorable / adverse) if adverse > 0 else None
        return ExtremeReplayScenarioResult(
            scenario=name,
            entered=True,
            entry_timestamp=entry_time.isoformat(),
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            maximum_favorable_excursion=favorable,
            maximum_adverse_excursion=adverse,
            recovery_seconds=event.recovery_seconds,
            holding_seconds=max(0.0, (end - entry_time).total_seconds()),
            distance_travelled=abs(exit_price - entry_price),
            potential_profit=favorable,
            potential_loss=potential_loss,
            reward_risk=reward_risk,
        )

    def _skipped(self, name: str, reason: str) -> ExtremeReplayScenarioResult:
        return ExtremeReplayScenarioResult(
            scenario=name,
            entered=False,
            entry_timestamp=None,
            direction="N/A",
            entry_price=None,
            exit_price=None,
            maximum_favorable_excursion=None,
            maximum_adverse_excursion=None,
            recovery_seconds=None,
            holding_seconds=None,
            distance_travelled=None,
            potential_profit=None,
            potential_loss=None,
            reward_risk=None,
            skipped_reason=reason,
        )

    def _statistics(self, events: list[ExtremeReplayEventResult]) -> ExtremeReplayStatistics:
        scenarios = [scenario for event in events for scenario in event.scenarios]
        entered = [scenario for scenario in scenarios if scenario.entered]
        potential_profits = [scenario.potential_profit for scenario in entered if scenario.potential_profit is not None]
        adverse = [
            scenario.maximum_adverse_excursion
            for scenario in entered
            if scenario.maximum_adverse_excursion is not None
        ]
        favorable = [
            scenario.maximum_favorable_excursion
            for scenario in entered
            if scenario.maximum_favorable_excursion is not None
        ]
        reward_risks = [scenario.reward_risk for scenario in entered if scenario.reward_risk is not None]
        return ExtremeReplayStatistics(
            events_count=len(events),
            scenario_count=len(scenarios),
            entered_replays_count=len(entered),
            average_potential_profit=mean(potential_profits) if potential_profits else None,
            median_potential_profit=median(potential_profits) if potential_profits else None,
            average_adverse_excursion=mean(adverse) if adverse else None,
            average_favorable_excursion=mean(favorable) if favorable else None,
            average_reward_risk=mean(reward_risks) if reward_risks else None,
            reward_risk_distribution=dict(Counter(self._reward_risk_bucket(value) for value in reward_risks)),
            assessment=self._assessment(len(events), reward_risks, potential_profits, adverse),
        )

    def _assessment(
        self,
        events_count: int,
        reward_risks: list[float],
        profits: list[float],
        adverse: list[float],
    ) -> str:
        if events_count < 10 or not reward_risks:
            average_profit = mean(profits) if profits else 0.0
            average_adverse = mean(adverse) if adverse else 0.0
            if events_count >= 10 and average_profit > 0 and average_adverse == 0:
                return "EXPLOITABLE_STRUCTURE"
            return "NEED_MORE_EXTREME_DATA"
        average_reward_risk = mean(reward_risks)
        average_profit = mean(profits) if profits else 0.0
        average_adverse = mean(adverse) if adverse else 0.0
        if average_reward_risk >= 1.5 and average_profit > average_adverse:
            return "EXPLOITABLE_STRUCTURE"
        return "NO_STATISTICALLY_STABLE_EDGE"

    def _cluster_labels(self, events: list[ExtremeMarketEvent]) -> dict[int, str]:
        labels: dict[int, str] = {}
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
        for group in groups:
            label = self.discovery._cluster_label(len(group))
            for event in group:
                labels[event.db_id] = label
        return labels

    def _velocity_spike_timestamp(
        self,
        snapshots: list[dict],
        start: datetime | None,
        end: datetime | None,
    ) -> datetime | None:
        for snapshot in self._snapshots_between(snapshots, start, end):
            if abs(float(snapshot.get("price_change_5_sec") or 0.0)) >= RECOVERY_VELOCITY_THRESHOLD:
                return self._parse_datetime(snapshot.get("timestamp"))
        return None

    def _flat_exit_timestamp(
        self,
        snapshots: list[dict],
        start: datetime | None,
        end: datetime | None,
    ) -> datetime | None:
        for snapshot in self._snapshots_between(snapshots, start, end):
            distance = abs(float(snapshot.get("distance_to_short_center") or 0.0))
            velocity = abs(float(snapshot.get("price_change_5_sec") or 0.0))
            if distance >= FLAT_EXIT_DISTANCE_THRESHOLD or velocity >= RECOVERY_VELOCITY_THRESHOLD:
                return self._parse_datetime(snapshot.get("timestamp"))
        return None

    def _future_prices(
        self,
        snapshots: list[dict],
        start: datetime,
        end: datetime,
        entry_price: float,
        exit_price: float,
    ) -> list[float]:
        prices = [entry_price]
        for snapshot in self._snapshots_between(snapshots, start, end):
            price = self._optional_float(snapshot.get("price"))
            if price is not None:
                prices.append(price)
        prices.append(exit_price)
        return prices

    def _excursions(self, direction: str, entry_price: float, prices: list[float]) -> tuple[float, float]:
        if direction == "BUY_USDC":
            favorable = max(price - entry_price for price in prices)
            adverse = max(entry_price - price for price in prices)
        else:
            favorable = max(entry_price - price for price in prices)
            adverse = max(price - entry_price for price in prices)
        return max(0.0, favorable), max(0.0, adverse)

    def _nearest_snapshot_at_or_after(
        self,
        snapshots: list[dict],
        start: datetime,
        end: datetime,
    ) -> dict | None:
        candidates = [
            snapshot for snapshot in snapshots
            if (timestamp := self._parse_datetime(snapshot.get("timestamp"))) is not None
            and start <= timestamp <= end
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: self._parse_datetime(item.get("timestamp")) or end)

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

    def _reward_risk_bucket(self, value: float) -> str:
        if value < 1:
            return "<1"
        if value < 2:
            return "1-2"
        if value < 3:
            return "2-3"
        return ">=3"

    def _write_report(self, report: ExtremeReplayReport, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "=== Extreme Replay Report ===",
            f"Profile: {report.profile}",
            f"Events: {report.statistics.events_count}",
            f"Replay scenarios: {report.statistics.scenario_count}",
            f"Entered replays: {report.statistics.entered_replays_count}",
            f"Average potential profit: {self._fmt(report.statistics.average_potential_profit)}",
            f"Median potential profit: {self._fmt(report.statistics.median_potential_profit)}",
            f"Average favorable excursion: {self._fmt(report.statistics.average_favorable_excursion)}",
            f"Average adverse excursion: {self._fmt(report.statistics.average_adverse_excursion)}",
            f"Average reward/risk: {self._fmt(report.statistics.average_reward_risk)}",
            f"Reward/risk distribution: {self._format_counter(report.statistics.reward_risk_distribution)}",
            f"Assessment: {report.statistics.assessment}",
            "",
            "Events:",
        ]
        for event in report.events:
            lines.append(
                f"- Event #{event.event_number} db_id={event.db_id} "
                f"start={event.start_timestamp} end={event.end_timestamp} "
                f"duration={self._fmt_seconds(event.duration_seconds)} "
                f"amplitude={event.amplitude_class} session={event.session} cluster={event.cluster_label}"
            )
            for scenario in event.scenarios:
                if not scenario.entered:
                    lines.append(f"  - {scenario.scenario}: skipped ({scenario.skipped_reason})")
                    continue
                lines.append(
                    f"  - {scenario.scenario}: direction={scenario.direction} "
                    f"entry={self._fmt(scenario.entry_price)} exit={self._fmt(scenario.exit_price)} "
                    f"MFE={self._fmt(scenario.maximum_favorable_excursion)} "
                    f"MAE={self._fmt(scenario.maximum_adverse_excursion)} "
                    f"profit={self._fmt(scenario.potential_profit)} "
                    f"loss={self._fmt(scenario.potential_loss)} "
                    f"RR={self._fmt(scenario.reward_risk)}"
                )
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _format_counter(self, values: dict[str, int]) -> str:
        if not values:
            return "N/A"
        return ", ".join(f"{key}={count}" for key, count in sorted(values.items()))

    def _fmt(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.8f}"

    def _fmt_seconds(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.0f}s"

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
