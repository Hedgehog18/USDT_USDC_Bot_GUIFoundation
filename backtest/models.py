from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestTrade:
    index: int
    action: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_profit: float
    fees: float
    net_profit: float


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    interval: str
    candles: int
    signals: int
    trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    total_fees: float
    net_profit: float
    roi: float
    final_value: float
    max_drawdown: float
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0


@dataclass(frozen=True)
class EquityPoint:
    index: int
    value: float


@dataclass(frozen=True)
class PeriodAnalytics:
    period: str
    start_value: float
    end_value: float
    profit: float
    roi: float
    trades: int
