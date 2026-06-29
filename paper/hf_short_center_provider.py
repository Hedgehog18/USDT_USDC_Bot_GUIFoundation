from collections import deque
from dataclasses import replace
from statistics import median


HF_SHORT_CENTER_MIN_SAMPLES = 20
HF_SHORT_CENTER_WINDOW = 60


class HFShortCenterMarketAnalyzer:
    """Paper-only rolling short-center adapter for the HF micro profile."""

    def __init__(
        self,
        analyzer,
        *,
        min_samples: int = HF_SHORT_CENTER_MIN_SAMPLES,
        window: int = HF_SHORT_CENTER_WINDOW,
    ) -> None:
        self.analyzer = analyzer
        self.min_samples = min_samples
        self.window = window
        self._prices = deque(maxlen=window)
        self.last_market_state = None

    def analyze_market(self):
        market_state = self.analyzer.analyze_market()
        price = float(getattr(market_state, "price", 0.0) or 0.0)
        previous_price = self._prices[-1] if self._prices else None
        if price > 0.0:
            self._prices.append(price)

        samples = len(self._prices)
        ready = samples >= self.min_samples
        short_center = float(median(self._prices)) if ready else 0.0
        short_low = min(self._prices) if self._prices else 0.0
        short_high = max(self._prices) if self._prices else 0.0
        short_position = self._short_position(price, short_low, short_high) if ready else 50.0

        updated_state = replace(
            market_state,
            short_low=short_low,
            short_high=short_high,
            short_center=short_center,
            short_position=short_position,
        )
        setattr(updated_state, "hf_short_center_samples", samples)
        setattr(updated_state, "hf_short_center_ready", ready)
        setattr(updated_state, "hf_entry_mode", "short_center")
        setattr(updated_state, "hf_previous_price", previous_price)
        setattr(updated_state, "hf_last_different_price", self._last_different_price(price))
        setattr(updated_state, "hf_price_buffer_unique_values", len(set(self._prices)))
        setattr(updated_state, "hf_flat_samples_count", self._flat_samples_count(price))
        setattr(updated_state, "hf_flat_price_buffer", len(set(self._prices)) == 1 if self._prices else False)
        self.last_market_state = updated_state
        return updated_state

    @property
    def last_data_source(self):
        return getattr(self.analyzer, "last_data_source", "UNKNOWN")

    @property
    def last_debug_info(self):
        return getattr(self.analyzer, "last_debug_info", {})

    @property
    def provider(self):
        return getattr(self.analyzer, "provider", None)

    @staticmethod
    def _short_position(price: float, short_low: float, short_high: float) -> float:
        if short_high <= short_low:
            return 50.0
        return max(0.0, min(100.0, ((price - short_low) / (short_high - short_low)) * 100.0))

    def _last_different_price(self, price: float) -> float | None:
        for item in reversed(self._prices):
            if item != price:
                return float(item)
        return None

    def _flat_samples_count(self, price: float) -> int:
        count = 0
        for item in reversed(self._prices):
            if item != price:
                break
            count += 1
        return count
