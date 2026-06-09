from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass(frozen=True)
class VolatilityMetrics:
    average_price: float
    standard_deviation: float
    relative_volatility: float
    volatility_regime: str


class VolatilityEngine:
    """Оцінка волатильності на основі списку цін закриття."""

    def analyze(self, prices: list[float]) -> VolatilityMetrics:
        if not prices:
            return VolatilityMetrics(
                average_price=0.0,
                standard_deviation=0.0,
                relative_volatility=0.0,
                volatility_regime="UNKNOWN",
            )

        avg_price = mean(prices)

        if len(prices) < 2 or avg_price <= 0:
            return VolatilityMetrics(
                average_price=avg_price,
                standard_deviation=0.0,
                relative_volatility=0.0,
                volatility_regime="LOW",
            )

        std = pstdev(prices)
        relative = std / avg_price

        if relative < 0.00005:
            regime = "LOW"
        elif relative < 0.0002:
            regime = "NORMAL"
        elif relative < 0.0005:
            regime = "HIGH"
        else:
            regime = "EXTREME"

        return VolatilityMetrics(
            average_price=avg_price,
            standard_deviation=std,
            relative_volatility=relative,
            volatility_regime=regime,
        )
