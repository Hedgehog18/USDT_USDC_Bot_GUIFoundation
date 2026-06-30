from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine

from analytics.micro_cycle_sim_engine import (
    MICRO_CYCLE_SCENARIOS,
    MicroCycleSimulationEngine,
    MicroCycleSimulationResult,
)


HF_GRID_DEFAULT_SCENARIO = "short_term_mean_reversion"
HF_GRID_DEFAULT_TARGET_PERCENT = 0.0005
HF_GRID_DEFAULT_MAX_HOLDING_SECONDS = 270.0
HF_GRID_DEFAULT_LAYER_SIZE = 10.0
HF_GRID_DEFAULT_MAX_LAYERS = 10


@dataclass(frozen=True)
class HFMicroGridClosedLayer:
    layer_id: int
    direction: str
    opened_at: str
    closed_at: str
    entry_price: float
    exit_price: float
    close_reason: str
    holding_seconds: float
    gross_profit: float
    net_profit: float
    max_unrealized_loss: float


@dataclass(frozen=True)
class HFMicroGridComparison:
    baseline_net_profit: float
    baseline_drawdown: float
    baseline_cycles_per_day: float
    grid_net_profit: float
    grid_drawdown: float
    grid_cycles_per_day: float
    capital_utilization: float
    verdict: str


@dataclass(frozen=True)
class HFMicroGridSimulationReport:
    scenario: str
    target_percent: float
    max_holding_seconds: float
    layer_size: float
    max_layers: int
    total_samples: int
    sample_span_hours: float
    opened_layers: int
    closed_layers: int
    active_layers: int
    average_capital_used: float
    maximum_capital_used: float
    average_layers_in_market: float
    maximum_simultaneous_layers: int
    gross_profit: float
    net_profit: float
    average_profit_per_layer: float
    median_profit: float
    max_drawdown: float
    worst_unrealized_drawdown: float
    longest_recovery_seconds: float
    all_layers_occupied_count: int
    all_layers_average_duration_seconds: float
    all_layers_longest_duration_seconds: float
    average_occupied_layers: float
    occupancy_histogram: dict[int, int]
    timeout_closes: int
    timeout_wins: int
    timeout_losses: int
    target_closes: int
    target_wins: int
    skipped_opportunities_no_layer: int
    skipped_opportunities_spacing: int
    cycles_per_hour: float
    estimated_cycles_per_day: float
    recommendation_score: float
    recommendation: str
    comparison: HFMicroGridComparison
    closed_layer_details: list[HFMicroGridClosedLayer]


@dataclass
class _GridLayer:
    layer_id: int
    direction: str
    entry_price: float
    target_price: float
    quantity: float
    opened_at: datetime | None
    max_unrealized_loss: float = 0.0


class HFMicroGridSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)
        self.micro_engine = MicroCycleSimulationEngine(database, config)

    def build_report(
        self,
        *,
        scenario: str = HF_GRID_DEFAULT_SCENARIO,
        target_percent: float = HF_GRID_DEFAULT_TARGET_PERCENT,
        max_holding_seconds: float = HF_GRID_DEFAULT_MAX_HOLDING_SECONDS,
        layer_size: float = HF_GRID_DEFAULT_LAYER_SIZE,
        max_layers: int = HF_GRID_DEFAULT_MAX_LAYERS,
    ) -> HFMicroGridSimulationReport:
        rows = self.micro_engine._load_rows()
        baseline = self.micro_engine.simulate(
            rows=rows,
            scenario=HF_GRID_DEFAULT_SCENARIO,
            target_percent=HF_GRID_DEFAULT_TARGET_PERCENT,
            max_holding_seconds=HF_GRID_DEFAULT_MAX_HOLDING_SECONDS,
        )
        return self.simulate(
            rows=rows,
            scenario=scenario,
            target_percent=target_percent,
            max_holding_seconds=max_holding_seconds,
            layer_size=layer_size,
            max_layers=max_layers,
            baseline=baseline,
        )

    def simulate(
        self,
        *,
        rows: list[dict],
        scenario: str,
        target_percent: float,
        max_holding_seconds: float,
        layer_size: float,
        max_layers: int,
        baseline: MicroCycleSimulationResult | None = None,
    ) -> HFMicroGridSimulationReport:
        self._validate(
            scenario=scenario,
            target_percent=target_percent,
            max_holding_seconds=max_holding_seconds,
            layer_size=layer_size,
            max_layers=max_layers,
        )

        active_layers: list[_GridLayer] = []
        closed_layers: list[HFMicroGridClosedLayer] = []
        opened_layers = 0
        next_layer_id = 1
        last_opened_at: datetime | None = None
        worst_unrealized_drawdown = 0.0
        skipped_no_layer = 0
        skipped_spacing = 0
        occupancy_histogram = {index: 0 for index in range(max_layers + 1)}
        occupancy_samples: list[int] = []
        all_layers_periods: list[float] = []
        all_layers_started_at: datetime | None = None
        previous_occupancy = 0

        for index, row in enumerate(rows):
            timestamp = row["parsed_timestamp"]
            still_active: list[_GridLayer] = []
            for layer in active_layers:
                profit = self._profit(layer, row["price"])
                layer.max_unrealized_loss = min(layer.max_unrealized_loss, profit.net_profit)
                worst_unrealized_drawdown = min(worst_unrealized_drawdown, profit.net_profit)
                close_reason = self._close_reason(layer, row, max_holding_seconds, profit.net_profit)
                if close_reason is None:
                    still_active.append(layer)
                    continue
                closed_layers.append(self._closed_layer(layer, row, close_reason, profit))
            active_layers = still_active

            direction = self.micro_engine._direction_for_scenario(row, index, scenario)
            if direction is not None:
                if len(active_layers) >= max_layers:
                    skipped_no_layer += 1
                elif last_opened_at is not None and self._holding_seconds(last_opened_at, timestamp) < max_holding_seconds:
                    skipped_spacing += 1
                else:
                    active_layers.append(
                        self._open_layer(
                            layer_id=next_layer_id,
                            direction=direction,
                            row=row,
                            target_percent=target_percent,
                            layer_size=layer_size,
                        )
                    )
                    opened_layers += 1
                    next_layer_id += 1
                    last_opened_at = timestamp

            occupancy = len(active_layers)
            occupancy_histogram[occupancy] = occupancy_histogram.get(occupancy, 0) + 1
            occupancy_samples.append(occupancy)
            if occupancy == max_layers and previous_occupancy < max_layers:
                all_layers_started_at = timestamp
            if previous_occupancy == max_layers and occupancy < max_layers and all_layers_started_at is not None:
                all_layers_periods.append(self._holding_seconds(all_layers_started_at, timestamp))
                all_layers_started_at = None
            previous_occupancy = occupancy

        if all_layers_started_at is not None and rows:
            all_layers_periods.append(self._holding_seconds(all_layers_started_at, rows[-1]["parsed_timestamp"]))

        sample_span_hours = self.micro_engine._sample_span_hours(rows)
        closed_count = len(closed_layers)
        gross_profit = sum(layer.gross_profit for layer in closed_layers)
        net_profit = sum(layer.net_profit for layer in closed_layers)
        net_values = [layer.net_profit for layer in closed_layers]
        target_closes = [layer for layer in closed_layers if layer.close_reason == "target"]
        timeout_closes = [layer for layer in closed_layers if layer.close_reason == "timeout"]
        cycles_per_hour = closed_count / sample_span_hours if sample_span_hours > 0 else 0.0
        max_drawdown = self._max_drawdown(closed_layers)
        average_layers = sum(occupancy_samples) / len(occupancy_samples) if occupancy_samples else 0.0
        maximum_layers = max(occupancy_samples, default=0)
        recommendation_score = self._score(
            net_profit=net_profit,
            drawdown=max_drawdown,
            cycles_per_day=cycles_per_hour * 24.0,
            active_layers=len(active_layers),
            max_layers=max_layers,
        )
        comparison = self._comparison(
            baseline=baseline,
            grid_net_profit=net_profit,
            grid_drawdown=max_drawdown,
            grid_cycles_per_day=cycles_per_hour * 24.0,
            average_capital_used=average_layers * layer_size,
            max_capital=max_layers * layer_size,
        )

        return HFMicroGridSimulationReport(
            scenario=scenario,
            target_percent=target_percent,
            max_holding_seconds=max_holding_seconds,
            layer_size=layer_size,
            max_layers=max_layers,
            total_samples=len(rows),
            sample_span_hours=sample_span_hours,
            opened_layers=opened_layers,
            closed_layers=closed_count,
            active_layers=len(active_layers),
            average_capital_used=average_layers * layer_size,
            maximum_capital_used=maximum_layers * layer_size,
            average_layers_in_market=average_layers,
            maximum_simultaneous_layers=maximum_layers,
            gross_profit=gross_profit,
            net_profit=net_profit,
            average_profit_per_layer=net_profit / closed_count if closed_count else 0.0,
            median_profit=float(median(net_values)) if net_values else 0.0,
            max_drawdown=max_drawdown,
            worst_unrealized_drawdown=worst_unrealized_drawdown,
            longest_recovery_seconds=self._longest_recovery_seconds(closed_layers),
            all_layers_occupied_count=len(all_layers_periods),
            all_layers_average_duration_seconds=(
                sum(all_layers_periods) / len(all_layers_periods) if all_layers_periods else 0.0
            ),
            all_layers_longest_duration_seconds=max(all_layers_periods, default=0.0),
            average_occupied_layers=average_layers,
            occupancy_histogram=occupancy_histogram,
            timeout_closes=len(timeout_closes),
            timeout_wins=sum(1 for layer in timeout_closes if layer.net_profit > 0),
            timeout_losses=sum(1 for layer in timeout_closes if layer.net_profit < 0),
            target_closes=len(target_closes),
            target_wins=sum(1 for layer in target_closes if layer.net_profit > 0),
            skipped_opportunities_no_layer=skipped_no_layer,
            skipped_opportunities_spacing=skipped_spacing,
            cycles_per_hour=cycles_per_hour,
            estimated_cycles_per_day=cycles_per_hour * 24.0,
            recommendation_score=recommendation_score,
            recommendation=self._recommendation(
                rows=rows,
                net_profit=net_profit,
                closed_count=closed_count,
                max_drawdown=max_drawdown,
                comparison=comparison,
            ),
            comparison=comparison,
            closed_layer_details=closed_layers,
        )

    def _open_layer(
        self,
        *,
        layer_id: int,
        direction: str,
        row: dict,
        target_percent: float,
        layer_size: float,
    ) -> _GridLayer:
        entry_price = row["price"]
        target_decimal = target_percent / 100.0
        return _GridLayer(
            layer_id=layer_id,
            direction=direction,
            entry_price=entry_price,
            target_price=(
                entry_price * (1.0 + target_decimal)
                if direction == "BUY"
                else entry_price * (1.0 - target_decimal)
            ),
            quantity=layer_size / entry_price,
            opened_at=row["parsed_timestamp"],
        )

    def _close_reason(
        self,
        layer: _GridLayer,
        row: dict,
        max_holding_seconds: float,
        net_profit: float,
    ) -> str | None:
        price = row["price"]
        if layer.direction == "BUY" and price >= layer.target_price:
            return "target"
        if layer.direction == "SELL" and price <= layer.target_price:
            return "target"
        if self._holding_seconds(layer.opened_at, row["parsed_timestamp"]) >= max_holding_seconds and net_profit >= 0:
            return "timeout"
        return None

    def _profit(self, layer: _GridLayer, close_price: float):
        direction = "BUY_USDC" if layer.direction == "BUY" else "SELL_USDC"
        return self.fee_engine.calculate_profit(
            direction=direction,
            open_price=layer.entry_price,
            close_price=close_price,
            quantity=layer.quantity,
            use_taker_fee=True,
        )

    def _closed_layer(self, layer: _GridLayer, row: dict, close_reason: str, profit) -> HFMicroGridClosedLayer:
        return HFMicroGridClosedLayer(
            layer_id=layer.layer_id,
            direction=layer.direction,
            opened_at=layer.opened_at.isoformat() if layer.opened_at else "",
            closed_at=row["parsed_timestamp"].isoformat() if row["parsed_timestamp"] else "",
            entry_price=layer.entry_price,
            exit_price=row["price"],
            close_reason=close_reason,
            holding_seconds=self._holding_seconds(layer.opened_at, row["parsed_timestamp"]),
            gross_profit=profit.gross_profit,
            net_profit=profit.net_profit,
            max_unrealized_loss=layer.max_unrealized_loss,
        )

    @staticmethod
    def _max_drawdown(layers: list[HFMicroGridClosedLayer]) -> float:
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for layer in layers:
            equity += layer.net_profit
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return max_drawdown

    @staticmethod
    def _longest_recovery_seconds(layers: list[HFMicroGridClosedLayer]) -> float:
        equity = 0.0
        peak = 0.0
        underwater_since: datetime | None = None
        longest = 0.0
        for layer in layers:
            closed_at = HFMicroGridSimulationEngine._parse_datetime(layer.closed_at)
            equity += layer.net_profit
            if equity >= peak:
                if underwater_since is not None and closed_at is not None:
                    longest = max(longest, HFMicroGridSimulationEngine._holding_seconds(underwater_since, closed_at))
                peak = equity
                underwater_since = None
            elif underwater_since is None:
                underwater_since = closed_at
        return longest

    @staticmethod
    def _comparison(
        *,
        baseline: MicroCycleSimulationResult | None,
        grid_net_profit: float,
        grid_drawdown: float,
        grid_cycles_per_day: float,
        average_capital_used: float,
        max_capital: float,
    ) -> HFMicroGridComparison:
        if baseline is None:
            return HFMicroGridComparison(
                baseline_net_profit=0.0,
                baseline_drawdown=0.0,
                baseline_cycles_per_day=0.0,
                grid_net_profit=grid_net_profit,
                grid_drawdown=grid_drawdown,
                grid_cycles_per_day=grid_cycles_per_day,
                capital_utilization=average_capital_used / max_capital if max_capital else 0.0,
                verdict="SIMILAR",
            )

        verdict = "SIMILAR"
        if grid_net_profit > baseline.net_profit * 1.10 and grid_drawdown >= baseline.max_drawdown_by_realized_equity * 2.0:
            verdict = "BETTER"
        elif grid_net_profit < baseline.net_profit * 0.90 or grid_drawdown < baseline.max_drawdown_by_realized_equity * 3.0:
            verdict = "WORSE"

        return HFMicroGridComparison(
            baseline_net_profit=baseline.net_profit,
            baseline_drawdown=baseline.max_drawdown_by_realized_equity,
            baseline_cycles_per_day=baseline.estimated_cycles_per_day,
            grid_net_profit=grid_net_profit,
            grid_drawdown=grid_drawdown,
            grid_cycles_per_day=grid_cycles_per_day,
            capital_utilization=average_capital_used / max_capital if max_capital else 0.0,
            verdict=verdict,
        )

    @staticmethod
    def _score(
        *,
        net_profit: float,
        drawdown: float,
        cycles_per_day: float,
        active_layers: int,
        max_layers: int,
    ) -> float:
        profit_score = max(min(net_profit * 1000.0, 3.0), -3.0)
        frequency_score = min(cycles_per_day / 500.0, 2.0)
        drawdown_penalty = min(abs(drawdown) * 500.0, 3.0)
        exposure_penalty = active_layers / max_layers if max_layers else 0.0
        return profit_score + frequency_score - drawdown_penalty - exposure_penalty

    @staticmethod
    def _recommendation(
        *,
        rows: list[dict],
        net_profit: float,
        closed_count: int,
        max_drawdown: float,
        comparison: HFMicroGridComparison,
    ) -> str:
        if not rows or closed_count < 5:
            return "NOT WORTH TESTING"
        if net_profit <= 0 or comparison.verdict == "WORSE":
            return "NOT WORTH TESTING"
        if comparison.verdict == "BETTER" and max_drawdown >= -0.01:
            return "STRONG PAPER CANDIDATE"
        return "PAPER CANDIDATE"

    @staticmethod
    def _validate(
        *,
        scenario: str,
        target_percent: float,
        max_holding_seconds: float,
        layer_size: float,
        max_layers: int,
    ) -> None:
        if scenario not in MICRO_CYCLE_SCENARIOS:
            raise ValueError(f"Unsupported micro-cycle scenario: {scenario}")
        if target_percent <= 0:
            raise ValueError("target_percent must be greater than 0.")
        if max_holding_seconds <= 0:
            raise ValueError("max_holding_seconds must be greater than 0.")
        if layer_size <= 0:
            raise ValueError("layer_size must be greater than 0.")
        if max_layers <= 0:
            raise ValueError("max_layers must be greater than 0.")

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _holding_seconds(opened_at: datetime | None, closed_at: datetime | None) -> float:
        if opened_at is None or closed_at is None:
            return 0.0
        return max((closed_at - opened_at).total_seconds(), 0.0)
