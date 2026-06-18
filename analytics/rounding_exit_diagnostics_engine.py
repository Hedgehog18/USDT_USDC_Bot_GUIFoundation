from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


@dataclass(frozen=True)
class RoundingExitCycleDetail:
    db_id: int
    direction: str
    opened_at: str
    age_seconds: float
    open_price: float
    target_price: float
    rounded_target_price: float
    current_price: float
    rounded_current_price: float
    strict_close: bool
    rounded_close: bool
    would_close_earlier: bool
    estimated_pnl: float
    profit_difference_vs_target: float


@dataclass(frozen=True)
class RoundingExitDiagnosticsReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    open_cycles_count: int
    would_close_earlier_count: int
    average_saved_holding_time_seconds: float
    profit_difference_vs_strict_comparison: float
    recommendation_score: float
    cycles: list[RoundingExitCycleDetail]


class RoundingExitDiagnosticsEngine:
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
    ) -> RoundingExitDiagnosticsReport:
        cycles = [
            self._build_detail(cycle, current_price)
            for cycle in self._load_open_cycles(profile)
        ]
        affected = [cycle for cycle in cycles if cycle.would_close_earlier]
        average_saved_holding = (
            sum(cycle.age_seconds for cycle in affected) / len(affected)
            if affected
            else 0.0
        )
        profit_difference = sum(cycle.profit_difference_vs_target for cycle in affected)
        recommendation_score = self._score(
            affected_count=len(affected),
            average_saved_holding_time_seconds=average_saved_holding,
            profit_difference_vs_target=profit_difference,
        )
        return RoundingExitDiagnosticsReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            open_cycles_count=len(cycles),
            would_close_earlier_count=len(affected),
            average_saved_holding_time_seconds=average_saved_holding,
            profit_difference_vs_strict_comparison=profit_difference,
            recommendation_score=recommendation_score,
            cycles=cycles,
        )

    def _build_detail(self, cycle: dict, current_price: float) -> RoundingExitCycleDetail:
        target_price = cycle["target_price"]
        strict_close = self._would_close(cycle["direction"], current_price, target_price)
        rounded_current = round(current_price, 7)
        rounded_target = round(target_price, 7)
        rounded_close = self._would_close(cycle["direction"], rounded_current, rounded_target)
        estimated_pnl = self._pnl(cycle, current_price)
        target_pnl = self._pnl(cycle, target_price)
        return RoundingExitCycleDetail(
            db_id=cycle["db_id"],
            direction=cycle["direction"],
            opened_at=cycle["opened_at"],
            age_seconds=cycle["age_seconds"],
            open_price=cycle["open_price"],
            target_price=target_price,
            rounded_target_price=rounded_target,
            current_price=current_price,
            rounded_current_price=rounded_current,
            strict_close=strict_close,
            rounded_close=rounded_close,
            would_close_earlier=rounded_close and not strict_close,
            estimated_pnl=estimated_pnl,
            profit_difference_vs_target=estimated_pnl - target_pnl,
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
            opened_at_text = clean_display_text(opened_at)
            opened_at_dt = datetime.fromisoformat(opened_at_text)
            now = datetime.now(tz=opened_at_dt.tzinfo) if opened_at_dt.tzinfo else datetime.now()
            cycles.append(
                {
                    "db_id": int(db_id),
                    "cycle_id": int(cycle_id),
                    "profile": strategy_profile,
                    "direction": clean_display_text(direction),
                    "open_price": float(open_price),
                    "target_price": float(close_price),
                    "quantity": float(quantity),
                    "opened_at": opened_at_text,
                    "age_seconds": max(0.0, (now - opened_at_dt).total_seconds()),
                }
            )
        return cycles

    def _pnl(self, cycle: dict, close_price: float) -> float:
        return self.fee_engine.calculate_profit(
            direction=cycle["direction"],
            open_price=cycle["open_price"],
            close_price=close_price,
            quantity=cycle["quantity"],
            use_taker_fee=True,
        ).net_profit

    @staticmethod
    def _would_close(direction: str, current_price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return current_price >= target_price
        if direction == "SELL_USDC":
            return current_price <= target_price
        return False

    @staticmethod
    def _score(
        *,
        affected_count: int,
        average_saved_holding_time_seconds: float,
        profit_difference_vs_target: float,
    ) -> float:
        close_bonus = affected_count * 1.0
        time_bonus = min(2.0, average_saved_holding_time_seconds / 3600.0)
        profit_penalty = abs(min(0.0, profit_difference_vs_target)) * 100.0
        return close_bonus + time_bonus - profit_penalty

