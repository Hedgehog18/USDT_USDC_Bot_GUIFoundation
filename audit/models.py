from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DecisionAuditRecord:
    timestamp: datetime
    decision: str
    allowed: bool
    reason: str
    risk_reason: str

    symbol: str
    price: float
    bid: float
    ask: float
    spread: float

    work_position: float
    short_position: float
    long_position: float

    market_activity_score: float
    cycle_prediction_score: float
    center_confidence: str
    market_regime: str

    explanation: str
    cycle_id: int | None = None
