from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager

from analytics.micro_cycle_grid_search_engine import MICRO_CYCLE_GRID_TARGETS
from analytics.micro_cycle_sim_engine import MicroCycleClosedCycle, MicroCycleSimulationEngine


@dataclass(frozen=True)
class TargetResolutionItem:
    requested_target_percent: float
    reference_price: float
    raw_target_distance: float
    raw_ticks: float
    floor_ticks: int
    ceil_ticks: int
    rounded_ticks: int
    floor_effective_target_percent: float
    ceil_effective_target_percent: float
    rounded_effective_target_percent: float
    buy_target_raw: float
    sell_target_raw: float
    buy_target_floor_tick: float
    buy_target_ceil_tick: float
    sell_target_floor_tick: float
    sell_target_ceil_tick: float
    minimum_price_move: float
    close_epsilon: float
    epsilon_ticks: float

    @property
    def has_sub_tick_distance(self) -> bool:
        return self.raw_ticks < 1.0


@dataclass(frozen=True)
class TargetPairComparison:
    first: TargetResolutionItem
    second: TargetResolutionItem
    identical_after_floor_normalization: bool
    identical_after_ceil_normalization: bool
    identical_after_rounding: bool
    identical_after_epsilon: bool
    identical_after_buy_target_calculation: bool
    identical_after_sell_target_calculation: bool
    warning: str


@dataclass(frozen=True)
class TargetSimulationComparison:
    first_target_percent: float
    second_target_percent: float
    scenario: str
    max_holding_seconds: float | None
    total_samples: int
    first_cycles: int
    second_cycles: int
    compared_cycles: int
    identical_outcomes: int
    different_outcomes: int
    similarity: float
    message: str


@dataclass(frozen=True)
class TargetResolutionDiagnosticsReport:
    symbol: str
    price_tick_size: float
    reference_price: float
    items: list[TargetResolutionItem]
    equivalent_groups: list[list[float]]


class TargetResolutionDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.sim_engine = MicroCycleSimulationEngine(database, config)

    def build_report(self, targets: list[float] | None = None) -> TargetResolutionDiagnosticsReport:
        reference_price = self._reference_price()
        items = [
            self.resolve_target(target_percent, reference_price=reference_price)
            for target_percent in (targets or list(MICRO_CYCLE_GRID_TARGETS))
        ]
        return TargetResolutionDiagnosticsReport(
            symbol=self.config.symbol,
            price_tick_size=self._tick_size(),
            reference_price=reference_price,
            items=items,
            equivalent_groups=self._equivalent_groups(items),
        )

    def compare(self, first_target_percent: float, second_target_percent: float) -> TargetPairComparison:
        reference_price = self._reference_price()
        first = self.resolve_target(first_target_percent, reference_price=reference_price)
        second = self.resolve_target(second_target_percent, reference_price=reference_price)
        identical_after_floor = first.floor_ticks == second.floor_ticks
        identical_after_ceil = first.ceil_ticks == second.ceil_ticks
        identical_after_rounding = first.rounded_ticks == second.rounded_ticks
        identical_after_epsilon = abs(first.raw_target_distance - second.raw_target_distance) <= first.close_epsilon
        identical_after_buy_target = abs(first.buy_target_raw - second.buy_target_raw) <= 1e-12
        identical_after_sell_target = abs(first.sell_target_raw - second.sell_target_raw) <= 1e-12
        warning = ""
        if identical_after_ceil or identical_after_rounding or identical_after_epsilon:
            warning = "Equivalent effective target."
        return TargetPairComparison(
            first=first,
            second=second,
            identical_after_floor_normalization=identical_after_floor,
            identical_after_ceil_normalization=identical_after_ceil,
            identical_after_rounding=identical_after_rounding,
            identical_after_epsilon=identical_after_epsilon,
            identical_after_buy_target_calculation=identical_after_buy_target,
            identical_after_sell_target_calculation=identical_after_sell_target,
            warning=warning,
        )

    def compare_simulation(
        self,
        first_target_percent: float,
        second_target_percent: float,
        *,
        scenario: str = "short_term_mean_reversion",
        max_holding_seconds: float | None = 270.0,
    ) -> TargetSimulationComparison:
        rows = self.sim_engine._load_rows()
        first = self.sim_engine.simulate(
            rows=rows,
            scenario=scenario,
            target_percent=first_target_percent,
            max_holding_seconds=max_holding_seconds,
        )
        second = self.sim_engine.simulate(
            rows=rows,
            scenario=scenario,
            target_percent=second_target_percent,
            max_holding_seconds=max_holding_seconds,
        )
        compared = max(len(first.cycles), len(second.cycles))
        identical = sum(
            1
            for left, right in zip(first.cycles, second.cycles)
            if self._cycle_key(left) == self._cycle_key(right)
        )
        different = compared - identical
        similarity = identical / compared if compared else 1.0
        if compared == 0:
            message = "No comparable cycles available for the current market data."
        elif similarity > 0.99:
            message = "These target values are effectively equivalent for the current market data."
        else:
            message = "These target values produce statistically different behaviour."
        return TargetSimulationComparison(
            first_target_percent=first_target_percent,
            second_target_percent=second_target_percent,
            scenario=scenario,
            max_holding_seconds=max_holding_seconds,
            total_samples=len(rows),
            first_cycles=len(first.cycles),
            second_cycles=len(second.cycles),
            compared_cycles=compared,
            identical_outcomes=identical,
            different_outcomes=different,
            similarity=similarity,
            message=message,
        )

    def resolve_target(self, target_percent: float, *, reference_price: float | None = None) -> TargetResolutionItem:
        if target_percent <= 0:
            raise ValueError("target_percent must be greater than 0.")
        price = reference_price if reference_price is not None else self._reference_price()
        tick = self._tick_size()
        raw_distance = price * (target_percent / 100.0)
        raw_ticks = raw_distance / tick if tick > 0 else 0.0
        floor_ticks = max(0, floor(raw_ticks))
        ceil_ticks = max(1, ceil(raw_ticks)) if raw_distance > 0 else 0
        rounded_ticks = max(1, round(raw_ticks)) if raw_distance > 0 else 0
        close_epsilon = self._close_epsilon()
        return TargetResolutionItem(
            requested_target_percent=target_percent,
            reference_price=price,
            raw_target_distance=raw_distance,
            raw_ticks=raw_ticks,
            floor_ticks=floor_ticks,
            ceil_ticks=ceil_ticks,
            rounded_ticks=rounded_ticks,
            floor_effective_target_percent=self._target_percent_for_ticks(floor_ticks, tick, price),
            ceil_effective_target_percent=self._target_percent_for_ticks(ceil_ticks, tick, price),
            rounded_effective_target_percent=self._target_percent_for_ticks(rounded_ticks, tick, price),
            buy_target_raw=price + raw_distance,
            sell_target_raw=price - raw_distance,
            buy_target_floor_tick=price + floor_ticks * tick,
            buy_target_ceil_tick=price + ceil_ticks * tick,
            sell_target_floor_tick=price - floor_ticks * tick,
            sell_target_ceil_tick=price - ceil_ticks * tick,
            minimum_price_move=tick,
            close_epsilon=close_epsilon,
            epsilon_ticks=close_epsilon / tick if tick > 0 else 0.0,
        )

    def _reference_price(self) -> float:
        rows = self.sim_engine._load_rows()
        prices = [row["price"] for row in rows if row.get("price", 0) > 0]
        return prices[-1] if prices else 1.0

    def _tick_size(self) -> float:
        return max(float(getattr(self.config, "price_tick_size", 0.0) or 0.0), 0.00000001)

    @staticmethod
    def _target_percent_for_ticks(ticks: int, tick_size: float, price: float) -> float:
        if price <= 0:
            return 0.0
        return (ticks * tick_size / price) * 100.0

    def _close_epsilon(self) -> float:
        # Paper runtime currently applies this only to the small-target profile.
        # This diagnostics command reports it as a precision reference without changing simulator behavior.
        return 0.00000010 if self.config.symbol.upper() == "USDCUSDT" else 0.0

    @staticmethod
    def _cycle_key(cycle: MicroCycleClosedCycle) -> tuple:
        return (
            cycle.opened_at,
            cycle.closed_at,
            cycle.direction,
            cycle.close_reason,
            round(cycle.entry_price, 12),
            round(cycle.exit_price, 12),
        )

    @staticmethod
    def _equivalent_groups(items: list[TargetResolutionItem]) -> list[list[float]]:
        groups: dict[int, list[float]] = {}
        for item in items:
            groups.setdefault(item.ceil_ticks, []).append(item.requested_target_percent)
        return [targets for targets in groups.values() if len(targets) > 1]
