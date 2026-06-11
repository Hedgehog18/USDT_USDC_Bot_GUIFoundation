from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
        direction = clean_display_text(direction)
        target_price = float(close_price)
        opened_at_text = clean_display_text(opened_at)
        opened_at_dt = datetime.fromisoformat(opened_at_text)
        now = datetime.now(tz=opened_at_dt.tzinfo) if opened_at_dt.tzinfo else datetime.now()
        age_seconds = max(0.0, (now - opened_at_dt).total_seconds())
        close_condition_met = self._close_condition_met(direction, current_price, target_price)
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
            profile=clean_display_text(strategy_profile or "UNKNOWN"),
            direction=direction,
            opened_at=opened_at_text,
            age_seconds=age_seconds,
            open_price=float(open_price),
            target_price=target_price,
            current_price=current_price,
            distance_to_target=distance,
            distance_to_target_percent=distance_percent,
            unrealized_pnl=unrealized_pnl,
            close_condition_met=close_condition_met,
            reason_not_closed=self._reason_not_closed(direction, close_condition_met, distance),
        )

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
    def _reason_not_closed(direction: str, close_condition_met: bool, distance: float) -> str:
        if close_condition_met:
            return "Close condition is met; waiting for the next paper close execution."
        if direction == "BUY_USDC":
            return f"Current price is {distance:.8f} below target price."
        if direction == "SELL_USDC":
            return f"Current price is {distance:.8f} above target price."
        return "Unsupported paper cycle direction."
