from dataclasses import dataclass

from config.config_manager import BotConfig
from market.order_book_engine import OrderBookMetrics


@dataclass(frozen=True)
class MarketHealth:
    score: float
    status: str
    reason: str


class MarketHealthEngine:
    """Оцінює, чи ринок придатний для відкриття нового циклу."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def analyze(
        self,
        spread: float,
        volatility_regime: str,
        order_book_metrics: OrderBookMetrics | None,
    ) -> MarketHealth:
        score = 100.0
        reasons: list[str] = []

        if spread <= 0:
            score -= 40
            reasons.append("Некоректний spread")

        if spread > self.config.max_allowed_spread:
            score -= 35
            reasons.append("Spread завеликий")

        if order_book_metrics is None or order_book_metrics.pressure == "UNKNOWN":
            score -= 25
            reasons.append("Немає якісного order book")
        elif order_book_metrics.liquidity_score < self.config.min_liquidity_score:
            score -= 25
            reasons.append("Низька ліквідність у стакані")

        if volatility_regime == "HIGH":
            score -= 20
            reasons.append("Висока волатильність")
        elif volatility_regime == "EXTREME":
            score -= 70
            reasons.append("Екстремальна волатильність")
        elif volatility_regime == "UNKNOWN":
            score -= 15
            reasons.append("Невідома волатильність")

        score = max(0.0, min(100.0, score))

        if score < self.config.min_market_health_score:
            status = "UNHEALTHY"
        elif score < 75:
            status = "CAUTION"
        else:
            status = "HEALTHY"

        reason = "; ".join(reasons) if reasons else "Ринок придатний для Demo-аналізу"

        return MarketHealth(
            score=score,
            status=status,
            reason=reason,
        )
