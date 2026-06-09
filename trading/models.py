from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CycleDirection(str, Enum):
    BUY_USDC = "BUY_USDC"
    SELL_USDC = "SELL_USDC"


class CycleStatus(str, Enum):
    CREATED = "CREATED"
    OPEN_ORDER_PLACED = "OPEN_ORDER_PLACED"
    OPEN_ORDER_FILLED = "OPEN_ORDER_FILLED"
    CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"
    CLOSE_ORDER_FILLED = "CLOSE_ORDER_FILLED"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CycleTimeStatus(str, Enum):
    NORMAL = "NORMAL"
    SLOW = "SLOW"
    STUCK = "STUCK"
    FROZEN = "FROZEN"
    CRITICAL = "CRITICAL"


@dataclass
class Cycle:
    id: int
    mode: str
    direction: CycleDirection
    status: CycleStatus
    time_status: CycleTimeStatus
    open_price: float
    close_price: float
    amount: float
    target_profit: float
    expected_profit: float
    actual_profit: float | None
    created_at: datetime
    open_filled_at: datetime | None = None
    close_filled_at: datetime | None = None
    closed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        end_time = self.closed_at or datetime.utcnow()
        return (end_time - self.created_at).total_seconds()
