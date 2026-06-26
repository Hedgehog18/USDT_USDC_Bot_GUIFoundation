from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


@dataclass(frozen=True)
class PaperOpenCycleDiagnostic:
    db_id: int
    cycle_id: int
    profile: str
    direction: str
    opened_at: str
    age_seconds: float
    open_price: float
    target_price: float
    current_price: float
    distance_to_target: float
    distance_to_target_percent: float
    unrealized_pnl: float
    close_epsilon: float
    effective_buy_close_price: float
    effective_sell_close_price: float
    close_condition_met: bool
    reason_not_closed: str


@dataclass(frozen=True)
class PaperOpenCyclesReport:
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    open_cycles: list[PaperOpenCycleDiagnostic]

    @property
    def open_cycles_count(self) -> int:
        return len(self.open_cycles)

    @property
    def nearest_to_target(self) -> PaperOpenCycleDiagnostic | None:
        if not self.open_cycles:
            return None
        return min(self.open_cycles, key=lambda item: abs(item.distance_to_target_percent))


class PaperOpenCycleDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(
        self,
        current_price: float,
        current_price_source: str = "UNKNOWN",
        current_price_timestamp: str = "UNKNOWN",
        limit: int = 100,
    ) -> PaperOpenCyclesReport:
        rows = self.database.load_open_paper_cycles(limit=limit)
        return PaperOpenCyclesReport(
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            open_cycles=[self._build_item(row, current_price) for row in rows],
        )

    def _build_item(self, row: tuple, current_price: float) -> PaperOpenCycleDiagnostic:
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
        profile = clean_display_text(strategy_profile or "UNKNOWN")
        direction = clean_display_text(direction)
        target_price = float(close_price)
        opened_at_text = clean_display_text(opened_at)
        opened_at_dt = datetime.fromisoformat(opened_at_text)
        now = datetime.now(tz=opened_at_dt.tzinfo) if opened_at_dt.tzinfo else datetime.now()
        age_seconds = max(0.0, (now - opened_at_dt).total_seconds())
        close_condition_met = self._close_condition_met(
            direction,
            current_price,
            target_price,
            profile,
        )
        close_epsilon = self._close_epsilon_for_profile(profile)
        distance = self._distance_to_target(direction, current_price, target_price)
        distance_percent = distance / target_price * 100.0 if target_price else 0.0
        profit = self.fee_engine.calculate_profit(
            direction=direction,
            open_price=float(open_price),
            close_price=current_price,
            quantity=float(quantity),
            use_taker_fee=True,
        )
        unrealized_pnl = profit.net_profit

        return PaperOpenCycleDiagnostic(
            db_id=int(db_id),
            cycle_id=int(cycle_id),
            profile=profile,
            direction=direction,
            opened_at=opened_at_text,
            age_seconds=age_seconds,
            open_price=float(open_price),
            target_price=target_price,
            current_price=current_price,
            distance_to_target=distance,
            distance_to_target_percent=distance_percent,
            unrealized_pnl=unrealized_pnl,
            close_epsilon=float(close_epsilon),
            effective_buy_close_price=float(Decimal(str(current_price)) + close_epsilon),
            effective_sell_close_price=float(Decimal(str(current_price)) - close_epsilon),
            close_condition_met=close_condition_met,
            reason_not_closed=self._reason_not_closed(direction, close_condition_met, distance),
        )

    @classmethod
    def _close_condition_met(
        cls,
        direction: str,
        current_price: float,
        target_price: float,
        profile: str = "strict_current",
    ) -> bool:
        close_epsilon = cls._close_epsilon_for_profile(profile)
        current_decimal = Decimal(str(current_price))
        target_decimal = Decimal(str(target_price))
        if direction == "BUY_USDC":
            return current_decimal + close_epsilon >= target_decimal
        if direction == "SELL_USDC":
            return current_decimal - close_epsilon <= target_decimal
        return False

    @staticmethod
    def _close_epsilon_for_profile(profile: str) -> Decimal:
        if profile == "mean_reversion_v2_small_target":
            return Decimal("0.00000010")
        return Decimal("0")

    @staticmethod
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _reason_not_closed(direction: str, close_condition_met: bool, distance: float) -> str:
        if close_condition_met:
            return "Close condition is met; waiting for the next paper close execution."
        if direction == "BUY_USDC":
            return f"Current price is {distance:.8f} below target price."
        if direction == "SELL_USDC":
            return f"Current price is {distance:.8f} above target price."
        return "Unsupported paper cycle direction."
