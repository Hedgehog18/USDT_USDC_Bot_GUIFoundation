from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PaperOrderSide(str, Enum):
    BUY_USDC = "BUY_USDC"
    SELL_USDC = "SELL_USDC"


class PaperOrderStatus(str, Enum):
    CREATED = "CREATED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass
class PaperOrder:
    id: int
    side: PaperOrderSide
    price: float
    quantity: float
    notional: float
    status: PaperOrderStatus
    reason: str
    created_at: datetime
    filled_at: datetime | None = None


@dataclass
class PaperPortfolio:
    usdt: float
    usdc: float
    usdc_price: float = 1.0

    @property
    def total_value(self) -> float:
        return self.usdt + self.usdc * self.usdc_price


@dataclass(frozen=True)
class PaperExecutionResult:
    order: PaperOrder
    portfolio: PaperPortfolio
    fee: float
    message: str


class PaperCycleStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


@dataclass
class PaperCycle:
    id: int
    direction: PaperOrderSide
    status: PaperCycleStatus
    open_price: float
    close_price: float
    quantity: float
    open_fee: float
    close_fee: float
    gross_profit: float
    net_profit: float
    opened_at: datetime
    closed_at: datetime | None = None
