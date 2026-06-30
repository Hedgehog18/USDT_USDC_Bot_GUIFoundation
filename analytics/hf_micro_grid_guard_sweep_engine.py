from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager

from analytics.hf_micro_grid_sim_engine import (
    HF_GRID_DEFAULT_LAYER_SIZE,
    HF_GRID_DEFAULT_MAX_HOLDING_SECONDS,
    HF_GRID_DEFAULT_MAX_LAYERS,
    HF_GRID_DEFAULT_SCENARIO,
    HF_GRID_DEFAULT_TARGET_PERCENT,
    HFMicroGridSimulationEngine,
    HFMicroGridSimulationReport,
)


HF_GRID_GUARD_MIN_LAYERS = (1, 2, 3, 4)
HF_GRID_GUARD_LOSS_THRESHOLDS = (0.0, -0.0005, -0.001, -0.002, -0.003, -0.005)


@dataclass(frozen=True)
class HFMicroGridGuardSweepReport:
    total_results: int
    grid_v1_reference: HFMicroGridSimulationReport
    results: list[HFMicroGridSimulationReport]
    top_by_score: list[HFMicroGridSimulationReport]
    top_by_net_profit_with_drawdown: list[HFMicroGridSimulationReport]
    top_by_lowest_drawdown_positive_net: list[HFMicroGridSimulationReport]
    balanced_candidates: list[HFMicroGridSimulationReport]


class HFMicroGridGuardSweepEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.sim_engine = HFMicroGridSimulationEngine(database, config)

    def run(
        self,
        *,
        top: int = 20,
        min_cycles_day: float = 150.0,
        max_drawdown: float = 0.01,
        max_average_capital: float = 50.0,
    ) -> HFMicroGridGuardSweepReport:
        if top <= 0:
            raise ValueError("top must be greater than 0.")
        if min_cycles_day < 0:
            raise ValueError("min_cycles_day must be 0 or greater.")
        if max_drawdown < 0:
            raise ValueError("max_drawdown must be 0 or greater.")
        if max_average_capital <= 0:
            raise ValueError("max_average_capital must be greater than 0.")

        rows = self.sim_engine.micro_engine._load_rows()
        baseline = self.sim_engine.micro_engine.simulate(
            rows=rows,
            scenario=HF_GRID_DEFAULT_SCENARIO,
            target_percent=HF_GRID_DEFAULT_TARGET_PERCENT,
            max_holding_seconds=HF_GRID_DEFAULT_MAX_HOLDING_SECONDS,
        )
        grid_v1 = self.sim_engine.simulate(
            rows=rows,
            scenario=HF_GRID_DEFAULT_SCENARIO,
            target_percent=HF_GRID_DEFAULT_TARGET_PERCENT,
            max_holding_seconds=180.0,
            layer_size=HF_GRID_DEFAULT_LAYER_SIZE,
            max_layers=HF_GRID_DEFAULT_MAX_LAYERS,
            baseline=baseline,
            directional_exposure_guard=False,
        )
        results = [
            self.sim_engine.simulate(
                rows=rows,
                scenario=HF_GRID_DEFAULT_SCENARIO,
                target_percent=HF_GRID_DEFAULT_TARGET_PERCENT,
                max_holding_seconds=180.0,
                layer_size=HF_GRID_DEFAULT_LAYER_SIZE,
                max_layers=HF_GRID_DEFAULT_MAX_LAYERS,
                baseline=baseline,
                directional_exposure_guard=True,
                guard_min_layers=min_layers,
                guard_loss_threshold=loss_threshold,
                grid_v1_reference=grid_v1,
            )
            for min_layers in HF_GRID_GUARD_MIN_LAYERS
            for loss_threshold in HF_GRID_GUARD_LOSS_THRESHOLDS
        ]

        return HFMicroGridGuardSweepReport(
            total_results=len(results),
            grid_v1_reference=grid_v1,
            results=results,
            top_by_score=sorted(results, key=lambda item: item.recommendation_score, reverse=True)[:top],
            top_by_net_profit_with_drawdown=sorted(
                [item for item in results if item.max_total_equity_drawdown >= -0.015],
                key=lambda item: item.net_profit,
                reverse=True,
            )[:top],
            top_by_lowest_drawdown_positive_net=sorted(
                [item for item in results if item.net_profit > 0],
                key=lambda item: item.max_total_equity_drawdown,
                reverse=True,
            )[:top],
            balanced_candidates=self._balanced_candidates(
                results,
                baseline_net_profit=baseline.net_profit,
                min_cycles_day=min_cycles_day,
                max_drawdown=max_drawdown,
                max_average_capital=max_average_capital,
                top=top,
            ),
        )

    def export_csv(self, path: str | Path, results: list[HFMicroGridSimulationReport]) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._csv_fields())
            writer.writeheader()
            for item in results:
                writer.writerow(self._row(item))
        return output_path

    @staticmethod
    def _balanced_candidates(
        results: list[HFMicroGridSimulationReport],
        *,
        baseline_net_profit: float,
        min_cycles_day: float,
        max_drawdown: float,
        max_average_capital: float,
        top: int,
    ) -> list[HFMicroGridSimulationReport]:
        return sorted(
            [
                item
                for item in results
                if item.net_profit > baseline_net_profit
                and item.max_total_equity_drawdown >= -max_drawdown
                and item.estimated_cycles_per_day >= min_cycles_day
                and item.average_capital_used <= max_average_capital
                and item.recommendation != "NOT WORTH TESTING"
            ],
            key=lambda item: (item.recommendation_score, item.net_profit),
            reverse=True,
        )[:top]

    def _row(self, item: HFMicroGridSimulationReport) -> dict:
        return {
            "guard_min_layers": item.guard_min_layers,
            "guard_loss_threshold": item.guard_loss_threshold,
            "net_profit": item.net_profit,
            "cycles_per_day": item.estimated_cycles_per_day,
            "max_total_equity_drawdown": item.max_total_equity_drawdown,
            "worst_open_basket_loss": item.worst_open_basket_loss,
            "max_simultaneous_layers": item.maximum_simultaneous_layers,
            "average_capital_used": item.average_capital_used,
            "directional_guard_blocks": item.directional_guard_blocks,
            "blocked_buy": item.directional_guard_buy_blocks,
            "blocked_sell": item.directional_guard_sell_blocks,
            "recommendation_score": item.recommendation_score,
            "recommendation": item.recommendation,
        }

    @staticmethod
    def _csv_fields() -> list[str]:
        return [
            "guard_min_layers",
            "guard_loss_threshold",
            "net_profit",
            "cycles_per_day",
            "max_total_equity_drawdown",
            "worst_open_basket_loss",
            "max_simultaneous_layers",
            "average_capital_used",
            "directional_guard_blocks",
            "blocked_buy",
            "blocked_sell",
            "recommendation_score",
            "recommendation",
        ]
