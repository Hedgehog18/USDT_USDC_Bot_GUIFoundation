from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketState:
    symbol: str
    price: float
    bid: float
    ask: float
    spread: float

    work_low: float
    work_high: float
    work_center: float
    work_position: float

    short_low: float
    short_high: float
    short_center: float
    short_position: float

    long_low: float
    long_high: float
    long_center: float
    long_position: float

    center_confidence: str
    center_alignment: str

    tick_activity_score: float
    center_crossing_score: float
    mean_reversion_score: float
    spread_stability_score: float
    corridor_quality_score: float
    market_activity_score: float

    market_regime: str
    created_at: datetime

    order_book_imbalance: float = 0.0
    order_book_pressure: str = "UNKNOWN"
    trade_volume_delta: float = 0.0
    micro_trend: str = "UNKNOWN"
    relative_volatility: float = 0.0
    volatility_regime: str = "UNKNOWN"
    market_health_score: float = 0.0
    market_health_status: str = "UNKNOWN"
    market_health_reason: str = ""
