from __future__ import annotations

from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


@dataclass(frozen=True)
class ExitToleranceProfile:
    name: str
    ticks: int | None = None
    target_distance_fraction: float | None = None


EXIT_TOLERANCE_PROFILES = (
    ExitToleranceProfile("0_ticks", ticks=0),
    ExitToleranceProfile("1_tick", ticks=1),
    ExitToleranceProfile("2_ticks", ticks=2),
    ExitToleranceProfile("5_ticks", ticks=5),
    ExitToleranceProfile("10_ticks", ticks=10),
    ExitToleranceProfile("25_percent_of_target_distance", target_distance_fraction=0.25),
    ExitToleranceProfile("50_percent_of_target_distance", target_distance_fraction=0.50),
)


@dataclass(frozen=True)
class OpenCycleExitToleranceDetail:
    db_id: int
    direction: str
    current_price: float
    target_price: float
    distance_to_target: float
    matching_tolerances: list[str]


@dataclass(frozen=True)
class ExitToleranceSimulationResult:
    tolerance_name: str
    tolerance_value: float
    affected_cycles: int
    would_close_now: int
    estimated_pnl: float
    difference_vs_strict_target: float
    closed_cycles_count: int
    open_cycles_remaining: int
    recommendation_score: float


@dataclass(frozen=True)
class ExitToleranceSimulationReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    open_cycles_count: int
    existing_closed_cycles_count: int
    results: list[ExitToleranceSimulationResult]
    open_cycle_details: list[OpenCycleExitToleranceDetail]
    recommended_tolerance: str | None


class ExitToleranceSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(
        self,
        *,
        profile: str,
        current_price: float,
        current_price_source: str = "UNKNOWN",
        current_price_timestamp: str = "UNKNOWN",
    ) -> ExitToleranceSimulationReport:
        open_cycles = self._load_open_cycles(profile)
        existing_closed_count = self._count_closed_cycles(profile)
        strict = self._evaluate_tolerance(
            tolerance=EXIT_TOLERANCE_PROFILES[0],
            open_cycles=open_cycles,
            current_price=current_price,
            existing_closed_count=existing_closed_count,
        )
        results = [
            self._evaluate_tolerance(
                tolerance=tolerance,
                open_cycles=open_cycles,
                current_price=current_price,
                existing_closed_count=existing_closed_count,
            )
            for tolerance in EXIT_TOLERANCE_PROFILES
        ]
        details = [
            self._build_open_cycle_detail(
                cycle=cycle,
                current_price=current_price,
                tolerances=EXIT_TOLERANCE_PROFILES,
            )
            for cycle in open_cycles
        ]
        recommended = self._recommend(results, strict)
        return ExitToleranceSimulationReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            open_cycles_count=len(open_cycles),
            existing_closed_cycles_count=existing_closed_count,
            results=results,
            open_cycle_details=details,
            recommended_tolerance=recommended,
        )

    def _evaluate_tolerance(
        self,
        *,
        tolerance: ExitToleranceProfile,
        open_cycles: list[dict],
        current_price: float,
        existing_closed_count: int,
    ) -> ExitToleranceSimulationResult:
        would_close = []
        affected = 0
        estimated_pnl = 0.0
        difference_vs_target = 0.0

        for cycle in open_cycles:
            tolerance_value = self._tolerance_value(tolerance, cycle)
            strict_close = self._would_close(cycle, current_price, 0.0)
            tolerance_close = self._would_close(cycle, current_price, tolerance_value)
            if not tolerance_close:
                continue

            would_close.append(cycle)
            if not strict_close:
                affected += 1
            current_pnl = self._pnl(cycle, current_price)
            target_pnl = self._pnl(cycle, cycle["target_price"])
            estimated_pnl += current_pnl
            difference_vs_target += current_pnl - target_pnl

        open_remaining = len(open_cycles) - len(would_close)
        score = self._score(
            estimated_pnl=estimated_pnl,
            difference_vs_target=difference_vs_target,
            would_close_now=len(would_close),
            affected_cycles=affected,
            open_remaining=open_remaining,
        )
        return ExitToleranceSimulationResult(
            tolerance_name=tolerance.name,
            tolerance_value=self._representative_tolerance_value(tolerance, open_cycles),
            affected_cycles=affected,
            would_close_now=len(would_close),
            estimated_pnl=estimated_pnl,
            difference_vs_strict_target=difference_vs_target,
            closed_cycles_count=existing_closed_count + len(would_close),
            open_cycles_remaining=open_remaining,
            recommendation_score=score,
        )

    def _build_open_cycle_detail(
        self,
        *,
        cycle: dict,
        current_price: float,
        tolerances: tuple[ExitToleranceProfile, ...],
    ) -> OpenCycleExitToleranceDetail:
        matching = [
            tolerance.name
            for tolerance in tolerances
            if self._would_close(cycle, current_price, self._tolerance_value(tolerance, cycle))
        ]
        return OpenCycleExitToleranceDetail(
            db_id=cycle["db_id"],
            direction=cycle["direction"],
            current_price=current_price,
            target_price=cycle["target_price"],
            distance_to_target=self._distance_to_target(cycle["direction"], current_price, cycle["target_price"]),
            matching_tolerances=matching,
        )

    def _load_open_cycles(self, profile: str) -> list[dict]:
        rows = self.database.load_open_paper_cycles(limit=1000)
        cycles: list[dict] = []
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
            strategy_profile = clean_display_text(strategy_profile or "UNKNOWN")
            if strategy_profile != profile:
                continue
            cycles.append(
                {
                    "db_id": int(db_id),
                    "cycle_id": int(cycle_id),
                    "profile": strategy_profile,
                    "direction": clean_display_text(direction),
                    "open_price": float(open_price),
                    "target_price": float(close_price),
                    "quantity": float(quantity),
                    "opened_at": clean_display_text(opened_at),
                }
            )
        return cycles

    def _count_closed_cycles(self, profile: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM paper_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'CLOSED_MANUAL')
                """,
                (profile,),
            ).fetchone()
        return int(row[0]) if row else 0

    def _pnl(self, cycle: dict, close_price: float) -> float:
        return self.fee_engine.calculate_profit(
            direction=cycle["direction"],
            open_price=cycle["open_price"],
            close_price=close_price,
            quantity=cycle["quantity"],
            use_taker_fee=True,
        ).net_profit

    def _tolerance_value(self, tolerance: ExitToleranceProfile, cycle: dict) -> float:
        if tolerance.ticks is not None:
            return tolerance.ticks * self.config.price_tick_size
        if tolerance.target_distance_fraction is not None:
            return abs(cycle["target_price"] - cycle["open_price"]) * tolerance.target_distance_fraction
        return 0.0

    def _representative_tolerance_value(
        self,
        tolerance: ExitToleranceProfile,
        cycles: list[dict],
    ) -> float:
        if tolerance.ticks is not None:
            return tolerance.ticks * self.config.price_tick_size
        values = [self._tolerance_value(tolerance, cycle) for cycle in cycles]
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _would_close(cycle: dict, current_price: float, tolerance: float) -> bool:
        if cycle["direction"] == "BUY_USDC":
            return current_price >= cycle["target_price"] - tolerance
        if cycle["direction"] == "SELL_USDC":
            return current_price <= cycle["target_price"] + tolerance
        return False

    @staticmethod
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _score(
        *,
        estimated_pnl: float,
        difference_vs_target: float,
        would_close_now: int,
        affected_cycles: int,
        open_remaining: int,
    ) -> float:
        early_exit_penalty = abs(min(0.0, difference_vs_target)) * 0.25
        remaining_penalty = open_remaining * 0.0005
        close_bonus = would_close_now * 0.001
        tolerance_bonus = affected_cycles * 0.0002
        return estimated_pnl + close_bonus + tolerance_bonus - early_exit_penalty - remaining_penalty

    @staticmethod
    def _recommend(
        results: list[ExitToleranceSimulationResult],
        strict: ExitToleranceSimulationResult,
    ) -> str | None:
        if not results:
            return None
        viable = [
            result
            for result in results
            if result.estimated_pnl > 0 and result.would_close_now >= strict.would_close_now
        ]
        selected = max(viable or results, key=lambda item: item.recommendation_score)
        return selected.tolerance_name
