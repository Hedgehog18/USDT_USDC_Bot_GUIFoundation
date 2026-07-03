from __future__ import annotations

from dataclasses import dataclass

from analytics.hf_velocity_filter_sim_engine import (
    HFVelocityFilterSimulationEngine,
    HFVelocityScenarioResult,
    HFVelocityCycle,
)
from storage.database_manager import DatabaseManager


REGIME_FILTER_VELOCITY_THRESHOLD = 0.00002
REGIME_NAMES = (
    "FLAT",
    "HIGH_VELOCITY",
    "FAST_DRIFT",
    "SLOW_DRIFT",
    "MICRO_RANGE",
    "LOW_VELOCITY",
    "UNKNOWN",
)


@dataclass(frozen=True)
class HFRegimeFilterResult:
    regime: str
    cycles_count: int
    net_profit: float
    net_profit_without_extreme: float
    win_rate: float
    timeout_losses: int
    filter_result: HFVelocityScenarioResult


@dataclass(frozen=True)
class HFRegimeFilterSimulationReport:
    profile: str
    since_id: int
    limit: int | None
    velocity_threshold: float
    total_cycles: int
    regimes: list[HFRegimeFilterResult]
    best_regime: str | None
    conclusion: str


class HFRegimeFilterSimulationEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.velocity_engine = HFVelocityFilterSimulationEngine(database)

    def simulate(
        self,
        *,
        profile: str,
        since_id: int = 0,
        limit: int | None = None,
        velocity_threshold: float = REGIME_FILTER_VELOCITY_THRESHOLD,
    ) -> HFRegimeFilterSimulationReport:
        cycles = self.velocity_engine._load_cycles(profile, since_id, limit)
        grouped = {name: [] for name in REGIME_NAMES}
        for cycle in cycles:
            grouped[self.classify_cycle(cycle)].append(cycle)

        results = [
            self._regime_result(name, grouped[name], velocity_threshold)
            for name in REGIME_NAMES
        ]
        useful = [
            result for result in results
            if result.filter_result.recommendation in {"STRONG_FILTER_CANDIDATE", "PROMISING_FILTER"}
        ]
        best = max(
            useful,
            key=lambda result: (
                result.filter_result.recommendation == "STRONG_FILTER_CANDIDATE",
                result.filter_result.net_improvement_vs_baseline,
            ),
            default=None,
        )
        return HFRegimeFilterSimulationReport(
            profile=profile,
            since_id=since_id,
            limit=limit,
            velocity_threshold=velocity_threshold,
            total_cycles=len(cycles),
            regimes=results,
            best_regime=None if best is None else best.regime,
            conclusion=self._conclusion(results, best),
        )

    def classify_cycle(self, cycle: HFVelocityCycle) -> str:
        velocity = cycle.price_velocity
        drift = cycle.short_term_drift
        entry_mode = str(cycle.hf_entry_mode or "").lower()
        if velocity is None or drift is None:
            return "UNKNOWN"
        if (
            cycle.flat_price_buffer
            or (cycle.price_buffer_unique_values is not None and cycle.price_buffer_unique_values <= 1)
            or "flat" in entry_mode
        ):
            return "FLAT"
        if abs(velocity) > 0.00002:
            return "HIGH_VELOCITY"
        if abs(drift) > 0.00002:
            return "FAST_DRIFT"
        if abs(velocity) > 0.00001 or abs(drift) > 0.00001:
            return "SLOW_DRIFT"
        if (
            cycle.price_buffer_unique_values is not None
            and cycle.price_buffer_unique_values <= 2
        ) or (
            cycle.flat_samples_count is not None
            and cycle.flat_samples_count >= 5
        ):
            return "MICRO_RANGE"
        return "LOW_VELOCITY"

    def _regime_result(
        self,
        regime: str,
        cycles: list[HFVelocityCycle],
        velocity_threshold: float,
    ) -> HFRegimeFilterResult:
        baseline_net = sum(cycle.net_profit for cycle in cycles if not cycle.is_extreme)
        filter_result = self.velocity_engine._scenario_result(
            f"block_velocity_gt_{velocity_threshold:.5f}",
            cycles,
            lambda cycle: self.velocity_engine._abs_gt(cycle.price_velocity, velocity_threshold),
            baseline_net,
        )
        non_extreme = [cycle for cycle in cycles if not cycle.is_extreme]
        wins = sum(1 for cycle in non_extreme if cycle.net_profit > 0)
        return HFRegimeFilterResult(
            regime=regime,
            cycles_count=len(cycles),
            net_profit=sum(cycle.net_profit for cycle in cycles),
            net_profit_without_extreme=baseline_net,
            win_rate=(wins / len(non_extreme)) if non_extreme else 0.0,
            timeout_losses=sum(1 for cycle in non_extreme if cycle.is_timeout_loss),
            filter_result=filter_result,
        )

    def _conclusion(
        self,
        results: list[HFRegimeFilterResult],
        best: HFRegimeFilterResult | None,
    ) -> str:
        populated = [result for result in results if result.cycles_count > 0]
        if not populated:
            return "No cycles available. Need more data."
        if best is None:
            return "Velocity filter provides no statistically significant benefit in any tested regime."
        if best.filter_result.recommendation == "STRONG_FILTER_CANDIDATE":
            return f"Velocity filter should only be considered during {best.regime} regime."
        return f"Velocity filter is promising only during {best.regime} regime; collect more data before runtime changes."
