from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


TARGET_REBASE_LOOKBACK = timedelta(hours=1)
TARGET_REBASE_SCENARIOS = (
    "no_rebase",
    "rebase_to_current_work_center",
    "rebase_to_1h_range_mid",
    "rebase_to_nearest_realistic_range_edge",
    "rebase_to_break_even_plus_min_profit",
)


@dataclass(frozen=True)
class TargetRebaseSnapshot:
    timestamp: datetime
    price: float
    work_center: float


@dataclass(frozen=True)
class OpenCycleTargetRebaseDiagnostic:
    db_id: int
    cycle_id: int
    direction: str
    open_price: float
    original_target: float
    current_price: float
    observed_1h_low: float | None
    observed_1h_high: float | None
    current_work_center: float | None
    target_outside_1h_range: bool
    suggested_rebased_target: float | None
    estimated_rebased_profit_or_loss: float | None
    would_close_if_rebased_now: bool


@dataclass(frozen=True)
class TargetRebaseScenarioResult:
    name: str
    affected_cycles: int
    would_close_now: int
    estimated_pnl: float
    remaining_open_exposure: int
    recommendation_score: float


@dataclass(frozen=True)
class TargetRebaseDiagnosticsReport:
    profile: str
    open_cycles: list[OpenCycleTargetRebaseDiagnostic]
    scenarios: list[TargetRebaseScenarioResult]


class TargetRebaseDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(self, *, profile: str) -> TargetRebaseDiagnosticsReport:
        snapshots = self._load_snapshots()
        latest_snapshot = snapshots[-1] if snapshots else None
        cycles = self._load_open_cycles(profile)
        diagnostics = [
            self._build_open_cycle_diagnostic(cycle, snapshots, latest_snapshot)
            for cycle in cycles
        ]
        return TargetRebaseDiagnosticsReport(
            profile=profile,
            open_cycles=diagnostics,
            scenarios=[
                self._evaluate_scenario(name, cycles, snapshots, latest_snapshot)
                for name in TARGET_REBASE_SCENARIOS
            ],
        )

    def _build_open_cycle_diagnostic(
        self,
        cycle: dict,
        snapshots: list[TargetRebaseSnapshot],
        latest_snapshot: TargetRebaseSnapshot | None,
    ) -> OpenCycleTargetRebaseDiagnostic:
        range_low, range_high = self._observed_range(snapshots, latest_snapshot.timestamp) if latest_snapshot else (None, None)
        suggested_target = self._scenario_target(
            "rebase_to_nearest_realistic_range_edge",
            cycle,
            latest_snapshot,
            range_low,
            range_high,
        )
        profit = (
            self.fee_engine.calculate_profit(
                direction=cycle["direction"],
                open_price=cycle["open_price"],
                close_price=suggested_target,
                quantity=cycle["quantity"],
                use_taker_fee=True,
            ).net_profit
            if suggested_target is not None
            else None
        )
        current_price = latest_snapshot.price if latest_snapshot else 0.0
        return OpenCycleTargetRebaseDiagnostic(
            db_id=cycle["db_id"],
            cycle_id=cycle["cycle_id"],
            direction=cycle["direction"],
            open_price=cycle["open_price"],
            original_target=cycle["original_target"],
            current_price=current_price,
            observed_1h_low=range_low,
            observed_1h_high=range_high,
            current_work_center=latest_snapshot.work_center if latest_snapshot else None,
            target_outside_1h_range=self._outside_range(cycle["original_target"], range_low, range_high),
            suggested_rebased_target=suggested_target,
            estimated_rebased_profit_or_loss=profit,
            would_close_if_rebased_now=(
                self._close_condition_met(cycle["direction"], current_price, suggested_target)
                if suggested_target is not None
                else False
            ),
        )

    def _evaluate_scenario(
        self,
        name: str,
        cycles: list[dict],
        snapshots: list[TargetRebaseSnapshot],
        latest_snapshot: TargetRebaseSnapshot | None,
    ) -> TargetRebaseScenarioResult:
        if latest_snapshot is None:
            return TargetRebaseScenarioResult(
                name=name,
                affected_cycles=0,
                would_close_now=0,
                estimated_pnl=0.0,
                remaining_open_exposure=0,
                recommendation_score=0.0,
            )

        range_low, range_high = self._observed_range(snapshots, latest_snapshot.timestamp)
        affected = 0
        would_close = 0
        estimated_pnl = 0.0
        for cycle in cycles:
            target = self._scenario_target(name, cycle, latest_snapshot, range_low, range_high)
            if target is None:
                continue
            is_affected = abs(target - cycle["original_target"]) > 1e-12
            if is_affected:
                affected += 1
            if self._close_condition_met(cycle["direction"], latest_snapshot.price, target):
                would_close += 1
            estimated_pnl += self.fee_engine.calculate_profit(
                direction=cycle["direction"],
                open_price=cycle["open_price"],
                close_price=target,
                quantity=cycle["quantity"],
                use_taker_fee=True,
            ).net_profit

        remaining = max(0, len(cycles) - would_close)
        return TargetRebaseScenarioResult(
            name=name,
            affected_cycles=affected,
            would_close_now=would_close,
            estimated_pnl=estimated_pnl,
            remaining_open_exposure=remaining,
            recommendation_score=self._recommendation_score(
                cycles_count=len(cycles),
                would_close=would_close,
                estimated_pnl=estimated_pnl,
                remaining_open_exposure=remaining,
            ),
        )

    def _scenario_target(
        self,
        name: str,
        cycle: dict,
        latest_snapshot: TargetRebaseSnapshot | None,
        range_low: float | None,
        range_high: float | None,
    ) -> float | None:
        if name == "no_rebase":
            return cycle["original_target"]
        if latest_snapshot is None:
            return None
        if name == "rebase_to_current_work_center":
            return latest_snapshot.work_center
        if name == "rebase_to_1h_range_mid":
            if range_low is None or range_high is None:
                return None
            return (range_low + range_high) / 2.0
        if name == "rebase_to_nearest_realistic_range_edge":
            if range_low is None or range_high is None:
                return None
            if cycle["direction"] == "BUY_USDC":
                return min(cycle["original_target"], range_high)
            if cycle["direction"] == "SELL_USDC":
                return max(cycle["original_target"], range_low)
            return cycle["original_target"]
        if name == "rebase_to_break_even_plus_min_profit":
            tick = max(float(self.config.price_tick_size), 0.00000001)
            if cycle["direction"] == "BUY_USDC":
                return cycle["open_price"] + tick
            if cycle["direction"] == "SELL_USDC":
                return cycle["open_price"] - tick
            return cycle["original_target"]
        return cycle["original_target"]

    def _load_open_cycles(self, profile: str) -> list[dict]:
        rows = self.database.load_open_paper_cycles(limit=1000)
        cycles = []
        for row in rows:
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

    def _load_snapshots(self) -> list[TargetRebaseSnapshot]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price, work_center
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            TargetRebaseSnapshot(
                timestamp=self._parse_timestamp(timestamp),
                price=float(price or 0.0),
                work_center=float(work_center or 0.0),
            )
            for timestamp, price, work_center in rows
        ]

    @staticmethod
    def _observed_range(
        snapshots: list[TargetRebaseSnapshot],
        timestamp: datetime,
    ) -> tuple[float | None, float | None]:
        window = [
            snapshot.price
            for snapshot in snapshots
            if timestamp - TARGET_REBASE_LOOKBACK <= snapshot.timestamp <= timestamp
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
    def _recommendation_score(
        *,
        cycles_count: int,
        would_close: int,
        estimated_pnl: float,
        remaining_open_exposure: int,
    ) -> float:
        if cycles_count == 0:
            return 0.0
        close_rate = would_close / cycles_count
        exposure_penalty = remaining_open_exposure / cycles_count
        pnl_score = 30.0 if estimated_pnl > 0 else 0.0
        score = (close_rate * 50.0) + pnl_score - (exposure_penalty * 10.0)
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def _parse_timestamp(value) -> datetime:
        parsed = datetime.fromisoformat(clean_display_text(value))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
