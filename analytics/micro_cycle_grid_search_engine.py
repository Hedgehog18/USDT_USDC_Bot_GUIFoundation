from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager

from analytics.micro_cycle_sim_engine import (
    MicroCycleSimulationEngine,
    MicroCycleSimulationResult,
)


MICRO_CYCLE_GRID_SCENARIOS = (
    "current_mean_reversion",
    "spread_only",
    "short_term_mean_reversion",
)

MICRO_CYCLE_GRID_TARGETS = (
    0.0005,
    0.00075,
    0.001,
    0.00125,
    0.0015,
    0.00175,
    0.002,
    0.0025,
    0.003,
    0.004,
    0.005,
)

MICRO_CYCLE_GRID_MAX_HOLDING_SECONDS = (
    60,
    90,
    120,
    150,
    180,
    210,
    240,
    270,
    300,
    330,
    360,
    420,
    480,
    600,
)


@dataclass(frozen=True)
class MicroCycleGridSearchReport:
    total_results: int
    results: list[MicroCycleSimulationResult]
    top_by_score: list[MicroCycleSimulationResult]
    top_by_net_profit: list[MicroCycleSimulationResult]
    top_by_cycles_per_day: list[MicroCycleSimulationResult]
    balanced_candidates: list[MicroCycleSimulationResult]


class MicroCycleGridSearchEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.sim_engine = MicroCycleSimulationEngine(database, config)

    def run(
        self,
        *,
        scenario: str | None = None,
        min_cycles_day: float = 100.0,
        max_drawdown: float = 0.005,
        top: int = 20,
    ) -> MicroCycleGridSearchReport:
        if top <= 0:
            raise ValueError("top must be greater than 0.")
        if min_cycles_day < 0:
            raise ValueError("min_cycles_day must be 0 or greater.")
        if max_drawdown < 0:
            raise ValueError("max_drawdown must be 0 or greater.")

        rows = self.sim_engine._load_rows()
        scenarios = [scenario] if scenario else list(MICRO_CYCLE_GRID_SCENARIOS)
        results = [
            self.sim_engine.simulate(
                rows=rows,
                scenario=item_scenario,
                target_percent=target,
                max_holding_seconds=float(max_holding_seconds),
            )
            for item_scenario in scenarios
            for target in MICRO_CYCLE_GRID_TARGETS
            for max_holding_seconds in MICRO_CYCLE_GRID_MAX_HOLDING_SECONDS
        ]

        return MicroCycleGridSearchReport(
            total_results=len(results),
            results=results,
            top_by_score=sorted(results, key=lambda item: item.recommendation_score, reverse=True)[:top],
            top_by_net_profit=sorted(results, key=lambda item: item.net_profit, reverse=True)[:top],
            top_by_cycles_per_day=sorted(
                [item for item in results if item.net_profit > 0],
                key=lambda item: item.estimated_cycles_per_day,
                reverse=True,
            )[:top],
            balanced_candidates=self._balanced_candidates(
                results,
                min_cycles_day=min_cycles_day,
                max_drawdown=max_drawdown,
                top=top,
            ),
        )

    def export_csv(self, path: str | Path, results: list[MicroCycleSimulationResult]) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._csv_fields())
            writer.writeheader()
            for item in results:
                writer.writerow(self._row(item))
        return output_path

    def all_results(
        self,
        *,
        scenario: str | None = None,
    ) -> list[MicroCycleSimulationResult]:
        rows = self.sim_engine._load_rows()
        scenarios = [scenario] if scenario else list(MICRO_CYCLE_GRID_SCENARIOS)
        return [
            self.sim_engine.simulate(
                rows=rows,
                scenario=item_scenario,
                target_percent=target,
                max_holding_seconds=float(max_holding_seconds),
            )
            for item_scenario in scenarios
            for target in MICRO_CYCLE_GRID_TARGETS
            for max_holding_seconds in MICRO_CYCLE_GRID_MAX_HOLDING_SECONDS
        ]

    @staticmethod
    def recommendation_for(item: MicroCycleSimulationResult) -> str:
        closed_count = item.closed_by_target + item.closed_by_timeout
        if item.total_samples == 0 or closed_count == 0:
            return "NEEDS_MORE_DATA"
        if item.net_profit <= 0 or item.max_drawdown_by_realized_equity < -0.01:
            return "NOT_VIABLE"
        if (
            item.estimated_cycles_per_day >= 300
            and item.profit_share_from_top_5_cycles <= 0.50
            and item.max_consecutive_losses <= 5
            and item.timeout_net_profit >= -0.02
        ):
            return "STRONG_CANDIDATE"
        return "PROMISING"

    def _balanced_candidates(
        self,
        results: list[MicroCycleSimulationResult],
        *,
        min_cycles_day: float,
        max_drawdown: float,
        top: int,
    ) -> list[MicroCycleSimulationResult]:
        return sorted(
            [
                item
                for item in results
                if item.net_profit > 0
                and item.estimated_cycles_per_day >= min_cycles_day
                and item.max_drawdown_by_realized_equity >= -max_drawdown
                and item.profit_share_from_top_5_cycles <= 0.50
                and item.timeout_net_profit >= -0.02
                and item.max_consecutive_losses <= 5
            ],
            key=lambda item: (item.recommendation_score, item.net_profit),
            reverse=True,
        )[:top]

    def _row(self, item: MicroCycleSimulationResult) -> dict:
        return {
            "scenario": item.scenario,
            "target": item.target_percent,
            "max_holding_seconds": item.max_holding_seconds,
            "opened": item.cycles_opened,
            "target_closed": item.closed_by_target,
            "timeout_closed": item.closed_by_timeout,
            "open_end": item.still_open_at_end,
            "win_rate": item.win_rate,
            "net_profit": item.net_profit,
            "avg_net": item.average_net_per_cycle,
            "avg_hold": item.average_holding_seconds,
            "median_hold": item.median_holding_seconds,
            "cycles_per_hour": item.cycles_per_hour,
            "cycles_per_day": item.estimated_cycles_per_day,
            "realized_drawdown": item.max_drawdown_by_realized_equity,
            "timeout_net": item.timeout_net_profit,
            "timeout_avg_net": item.timeout_avg_net,
            "timeout_loss_count": item.timeout_loss_count,
            "max_loss_streak": item.max_consecutive_losses,
            "max_timeout_loss_streak": item.max_consecutive_timeout_losses,
            "top5_profit_share": item.profit_share_from_top_5_cycles,
            "recommendation": self.recommendation_for(item),
            "recommendation_score": item.recommendation_score,
        }

    @staticmethod
    def _csv_fields() -> list[str]:
        return [
            "scenario",
            "target",
            "max_holding_seconds",
            "opened",
            "target_closed",
            "timeout_closed",
            "open_end",
            "win_rate",
            "net_profit",
            "avg_net",
            "avg_hold",
            "median_hold",
            "cycles_per_hour",
            "cycles_per_day",
            "realized_drawdown",
            "timeout_net",
            "timeout_avg_net",
            "timeout_loss_count",
            "max_loss_streak",
            "max_timeout_loss_streak",
            "top5_profit_share",
            "recommendation",
            "recommendation_score",
        ]
