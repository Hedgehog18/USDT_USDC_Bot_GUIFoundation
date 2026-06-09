from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ActivityMetrics:
    tick_activity_score: float
    center_crossing_score: float
    mean_reversion_score: float
    spread_stability_score: float
    corridor_quality_score: float
    market_activity_score: float


class ActivityEngine:
    def calculate_tick_activity_score(self, prices: Sequence[float]) -> float:
        if len(prices) < 2:
            return 0.0
        changes = sum(1 for i in range(1, len(prices)) if prices[i] != prices[i - 1])
        return min(100.0, (changes / 50) * 100)

    def calculate_center_crossing_score(self, prices: Sequence[float], center: float) -> float:
        if len(prices) < 2:
            return 0.0

        crossings = 0
        previous_side = self._side(prices[0], center)

        for price in prices[1:]:
            current_side = self._side(price, center)
            if previous_side != 0 and current_side != 0 and current_side != previous_side:
                crossings += 1
            if current_side != 0:
                previous_side = current_side

        return min(100.0, (crossings / 20) * 100)

    def calculate_mean_reversion_score(self, prices: Sequence[float], center: float) -> float:
        if not prices:
            return 0.0
        max_deviation = max(abs(p - center) for p in prices)
        if max_deviation == 0:
            return 100.0
        normalized = [abs(p - center) / max_deviation for p in prices]
        average_distance = sum(normalized) / len(normalized)
        return max(0.0, min(100.0, (1 - average_distance) * 100))

    def calculate_spread_stability_score(self, spreads: Sequence[float]) -> float:
        if not spreads:
            return 0.0
        avg_spread = sum(spreads) / len(spreads)
        if avg_spread == 0:
            return 100.0
        max_spread = max(spreads)
        spread_ratio = max_spread / avg_spread
        score = 100 - ((spread_ratio - 1) / 2) * 100
        return max(0.0, min(100.0, score))

    def calculate_corridor_quality_score(self, prices: Sequence[float]) -> float:
        if len(prices) < 3:
            return 0.0
        return max(0.0, min(100.0, (len(set(prices)) / len(prices)) * 100))

    def calculate_activity_metrics(self, prices: Sequence[float], spreads: Sequence[float], center: float) -> ActivityMetrics:
        tick_score = self.calculate_tick_activity_score(prices)
        crossing_score = self.calculate_center_crossing_score(prices, center)
        reversion_score = self.calculate_mean_reversion_score(prices, center)
        spread_score = self.calculate_spread_stability_score(spreads)
        corridor_score = self.calculate_corridor_quality_score(prices)

        market_activity_score = (
            tick_score * 0.20
            + crossing_score * 0.30
            + reversion_score * 0.30
            + spread_score * 0.10
            + corridor_score * 0.10
        )

        return ActivityMetrics(
            tick_activity_score=tick_score,
            center_crossing_score=crossing_score,
            mean_reversion_score=reversion_score,
            spread_stability_score=spread_score,
            corridor_quality_score=corridor_score,
            market_activity_score=market_activity_score,
        )

    @staticmethod
    def _side(price: float, center: float) -> int:
        if price > center:
            return 1
        if price < center:
            return -1
        return 0
