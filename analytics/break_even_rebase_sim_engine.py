from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


BREAK_EVEN_REBASE_LOOKBACK = timedelta(hours=1)
BREAK_EVEN_REBASE_SCENARIOS = (
    "no_rebase",
    "break_even_plus_1_tick",
    "break_even_plus_0_001_percent",
    "break_even_plus_0_0025_percent",
    "break_even_plus_0_005_percent",
)


@dataclass(frozen=True)
class BreakEvenRebaseSnapshot:
    timestamp: datetime
    price: float


@dataclass(frozen=True)
class BreakEvenRebaseScenarioResult:
    name: str
    affected_open_cycles: int
    would_close_now: int
    estimated_realized_pnl: float
    remaining_open_exposure: int
    average_distance_to_rebased_target: float | None
    avoided_loss_vs_nearest_range_edge: float
    recommendation_score: float


@dataclass(frozen=True)
class BreakEvenRebaseSimulationReport:
    profile: str
    open_cycles_count: int
    current_price: float | None
    observed_1h_low: float | None
    observed_1h_high: float | None
    scenarios: list[BreakEvenRebaseScenarioResult]


class BreakEvenRebaseSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(self, *, profile: str) -> BreakEvenRebaseSimulationReport:
        snapshots = self._load_snapshots()
        latest_snapshot = snapshots[-1] if snapshots else None
        cycles = self._load_open_cycles(profile)
        range_low, range_high = (
            self._observed_range(snapshots, latest_snapshot.timestamp)
            if latest_snapshot is not None
            else (None, None)
        )
        return BreakEvenRebaseSimulationReport(
            profile=profile,
            open_cycles_count=len(cycles),
            current_price=latest_snapshot.price if latest_snapshot else None,
            observed_1h_low=range_low,
            observed_1h_high=range_high,
            scenarios=[
                self._evaluate_scenario(name, cycles, latest_snapshot, range_low, range_high)
                for name in BREAK_EVEN_REBASE_SCENARIOS
            ],
        )

    def _evaluate_scenario(
        self,
        name: str,
        cycles: list[dict],
        latest_snapshot: BreakEvenRebaseSnapshot | None,
        range_low: float | None,
        range_high: float | None,
    ) -> BreakEvenRebaseScenarioResult:
        if latest_snapshot is None:
            return BreakEvenRebaseScenarioResult(
                name=name,
                affected_open_cycles=0,
                would_close_now=0,
                estimated_realized_pnl=0.0,
                remaining_open_exposure=0,
                average_distance_to_rebased_target=None,
                avoided_loss_vs_nearest_range_edge=0.0,
                recommendation_score=0.0,
            )

        affected = 0
        would_close = 0
        estimated_pnl = 0.0
        distances: list[float] = []
        nearest_edge_pnl = 0.0
        for cycle in cycles:
            is_unrealistic = self._outside_range(cycle["original_target"], range_low, range_high)
            target = self._scenario_target(name, cycle, is_unrealistic)
            if target is None:
                continue
            if is_unrealistic and abs(target - cycle["original_target"]) > 1e-12:
                affected += 1
            if self._close_condition_met(cycle["direction"], latest_snapshot.price, target):
                would_close += 1
            estimated_pnl += self._profit(cycle, target)
            distances.append(abs(self._distance_to_target(cycle["direction"], latest_snapshot.price, target)))
            nearest_edge_pnl += self._profit(
                cycle,
                self._nearest_realistic_range_edge(cycle, range_low, range_high),
            )

        remaining = max(0, len(cycles) - would_close)
        avoided_loss = estimated_pnl - nearest_edge_pnl
        return BreakEvenRebaseScenarioResult(
            name=name,
            affected_open_cycles=affected,
            would_close_now=would_close,
            estimated_realized_pnl=estimated_pnl,
            remaining_open_exposure=remaining,
            average_distance_to_rebased_target=self._average(distances),
            avoided_loss_vs_nearest_range_edge=avoided_loss,
            recommendation_score=self._recommendation_score(
                cycles_count=len(cycles),
                would_close=would_close,
                estimated_pnl=estimated_pnl,
                remaining_open_exposure=remaining,
                avoided_loss=avoided_loss,
            ),
        )

    def _scenario_target(self, name: str, cycle: dict, is_unrealistic: bool) -> float | None:
        if name == "no_rebase" or not is_unrealistic:
            return cycle["original_target"]
        if name == "break_even_plus_1_tick":
            profit_distance = max(float(self.config.price_tick_size), 0.00000001)
        elif name == "break_even_plus_0_001_percent":
            profit_distance = cycle["open_price"] * 0.00001
        elif name == "break_even_plus_0_0025_percent":
            profit_distance = cycle["open_price"] * 0.000025
        elif name == "break_even_plus_0_005_percent":
            profit_distance = cycle["open_price"] * 0.00005
        else:
            return cycle["original_target"]

        if cycle["direction"] == "BUY_USDC":
            return cycle["open_price"] + profit_distance
        if cycle["direction"] == "SELL_USDC":
            return cycle["open_price"] - profit_distance
        return cycle["original_target"]

    def _nearest_realistic_range_edge(
        self,
        cycle: dict,
        range_low: float | None,
        range_high: float | None,
    ) -> float:
        if range_low is None or range_high is None:
            return cycle["original_target"]
        if cycle["direction"] == "BUY_USDC":
            return min(cycle["original_target"], range_high)
        if cycle["direction"] == "SELL_USDC":
            return max(cycle["original_target"], range_low)
        return cycle["original_target"]

    def _profit(self, cycle: dict, close_price: float) -> float:
        return self.fee_engine.calculate_profit(
            direction=cycle["direction"],
            open_price=cycle["open_price"],
            close_price=close_price,
            quantity=cycle["quantity"],
            use_taker_fee=True,
        ).net_profit

    def _load_open_cycles(self, profile: str) -> list[dict]:
        cycles = []
        for row in self.database.load_open_paper_cycles(limit=1000):
            (
                db_id,
                _timestamp,
                cycle_id,
                strategy_profile,
                direction,
                _status,
                open_price,
                close_price,
                quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                _net_profit,
                opened_at,
                _closed_at,
            ) = row
            if clean_display_text(strategy_profile or "") != profile:
                continue
            cycles.append(
                {
                    "db_id": int(db_id),
                    "cycle_id": int(cycle_id),
                    "direction": clean_display_text(direction),
                    "open_price": float(open_price),
                    "original_target": float(close_price),
                    "quantity": float(quantity),
                    "opened_at": clean_display_text(opened_at),
                }
            )
        return cycles

    def _load_snapshots(self) -> list[BreakEvenRebaseSnapshot]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            BreakEvenRebaseSnapshot(
                timestamp=self._parse_timestamp(timestamp),
                price=float(price or 0.0),
            )
            for timestamp, price in rows
        ]

    @staticmethod
    def _observed_range(
        snapshots: list[BreakEvenRebaseSnapshot],
        timestamp: datetime,
    ) -> tuple[float | None, float | None]:
        window = [
            snapshot.price
            for snapshot in snapshots
            if timestamp - BREAK_EVEN_REBASE_LOOKBACK <= snapshot.timestamp <= timestamp
        ]
        if not window:
            return None, None
        return min(window), max(window)

    @staticmethod
    def _outside_range(value: float, range_low: float | None, range_high: float | None) -> bool:
        if range_low is None or range_high is None:
            return False
        return value < range_low or value > range_high

    @staticmethod
    def _close_condition_met(direction: str, current_price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return current_price >= target_price
        if direction == "SELL_USDC":
            return current_price <= target_price
        return False

    @staticmethod
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _recommendation_score(
        *,
        cycles_count: int,
        would_close: int,
        estimated_pnl: float,
        remaining_open_exposure: int,
        avoided_loss: float,
    ) -> float:
        if cycles_count == 0:
            return 0.0
        close_rate = would_close / cycles_count
        exposure_penalty = remaining_open_exposure / cycles_count
        pnl_score = 30.0 if estimated_pnl > 0 else 0.0
        avoided_loss_score = 20.0 if avoided_loss > 0 else 0.0
        score = (close_rate * 40.0) + pnl_score + avoided_loss_score - (exposure_penalty * 10.0)
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _parse_timestamp(value) -> datetime:
        parsed = datetime.fromisoformat(clean_display_text(value))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
