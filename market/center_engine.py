from dataclasses import dataclass
from statistics import mean, median
from typing import Sequence


@dataclass(frozen=True)
class Corridor:
    low: float
    high: float
    center_mean: float
    center_median: float
    center_range: float
    active_center: float
    position: float
    range_value: float


class CenterEngine:
    def build_corridor(self, prices: Sequence[float], current_price: float) -> Corridor:
        if not prices:
            raise ValueError("Список цін не може бути порожнім.")

        low = min(prices)
        high = max(prices)
        range_value = high - low
        center_mean = mean(prices)
        center_median = median(prices)
        center_range = (low + high) / 2
        active_center = center_median
        position = self.calculate_corridor_position(current_price, low, high)

        return Corridor(
            low=low,
            high=high,
            center_mean=center_mean,
            center_median=center_median,
            center_range=center_range,
            active_center=active_center,
            position=position,
            range_value=range_value,
        )

    @staticmethod
    def calculate_corridor_position(price: float, low: float, high: float) -> float:
        if high == low:
            return 50.0
        position = ((price - low) / (high - low)) * 100
        return max(0.0, min(100.0, position))

    @staticmethod
    def calculate_center_confidence(*centers: float, range_value: float) -> str:
        if not centers or range_value <= 0:
            return "LOW"
        deviation = max(centers) - min(centers)
        if deviation < range_value * 0.10:
            return "HIGH"
        if deviation < range_value * 0.25:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def calculate_center_alignment(work_center: float, short_center: float, long_center: float) -> str:
        if work_center == short_center == long_center:
            return "FLAT"
        if work_center > short_center > long_center:
            return "UP"
        if work_center < short_center < long_center:
            return "DOWN"
        return "MIXED"
