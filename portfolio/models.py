from dataclasses import dataclass
from datetime import datetime


@dataclass
class BotBudget:
    usdt_budget: float
    usdc_budget: float
    usdc_price: float = 1.0

    @property
    def usdc_value(self) -> float:
        return self.usdc_budget * self.usdc_price

    @property
    def total_value(self) -> float:
        return self.usdt_budget + self.usdc_value


@dataclass(frozen=True)
class BotBudgetEvent:
    event_type: str
    asset: str
    amount: float
    value_usdt: float
    note: str
    created_at: datetime
