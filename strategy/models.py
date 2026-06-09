from dataclasses import dataclass
from datetime import datetime


@dataclass
class TradeDecision:
    action: str
    reason: str
    confidence: str
    cycle_prediction_score: float
    recommended_trade_size: float
    target_profit: float
    created_at: datetime


@dataclass
class RiskResult:
    allowed: bool
    reason: str
    risk_level: str
