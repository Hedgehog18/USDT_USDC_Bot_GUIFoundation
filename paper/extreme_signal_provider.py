from __future__ import annotations

from collections import deque
from dataclasses import replace

from analytics.market_session_diagnostics_engine import MarketSessionDiagnosticsEngine


EXTREME_PROFILE_NAME = "extreme_strategy_v1"
EXTREME_REQUIRED_SESSION = "NEW_YORK"
EXTREME_TARGET_PROFIT = 0.00001
EXTREME_MAX_HOLDING_SECONDS = 60.0
EXTREME_COOLDOWN_SECONDS = 270.0
EXTREME_VELOCITY_THRESHOLD = 0.000001
EXTREME_COMPRESSION_MAX_UNIQUE_VALUES = 2
EXTREME_COMPRESSION_MIN_FLAT_SAMPLES = 3
EXTREME_BUFFER_WINDOW = 60
EXTREME_MIN_SAMPLES = 5
EXTREME_EXPECTED_DIRECTION = "SELL_USDC"
EXTREME_LEAD_TIME_SECONDS = 5.0


class ExtremeSignalMarketAnalyzer:
    """Paper-only live signal adapter for the Extreme Strategy v1 research profile."""

    def __init__(
        self,
        analyzer,
        *,
        window: int = EXTREME_BUFFER_WINDOW,
        min_samples: int = EXTREME_MIN_SAMPLES,
        velocity_threshold: float = EXTREME_VELOCITY_THRESHOLD,
        required_session: str = EXTREME_REQUIRED_SESSION,
    ) -> None:
        self.analyzer = analyzer
        self.window = window
        self.min_samples = min_samples
        self.velocity_threshold = velocity_threshold
        self.required_session = required_session
        self._prices = deque(maxlen=window)
        self.last_market_state = None

    def analyze_market(self):
        market_state = self.analyzer.analyze_market()
        price = float(getattr(market_state, "price", 0.0) or 0.0)
        previous_price = self._prices[-1] if self._prices else None
        pre_unique_values = len(set(self._prices))
        pre_flat_samples = self._flat_samples_count(previous_price) if previous_price is not None else 0

        if price > 0.0:
            self._prices.append(price)

        session = MarketSessionDiagnosticsEngine.classify_session(getattr(market_state, "created_at").hour)
        price_velocity = (price - previous_price) if previous_price is not None else 0.0
        velocity_direction = "DOWN" if price_velocity < 0 else "UP" if price_velocity > 0 else "FLAT"
        session_signal = session == self.required_session
        velocity_spike_signal = price_velocity <= -abs(self.velocity_threshold)
        compression_signal = (
            len(self._prices) >= self.min_samples
            and (
                pre_flat_samples >= EXTREME_COMPRESSION_MIN_FLAT_SAMPLES
                or 0 < pre_unique_values <= EXTREME_COMPRESSION_MAX_UNIQUE_VALUES
            )
        )
        signal_detected = session_signal and velocity_spike_signal and compression_signal
        signal_strength = self._signal_strength(
            session_signal=session_signal,
            velocity_spike_signal=velocity_spike_signal,
            compression_signal=compression_signal,
            price_velocity=price_velocity,
        )

        updated_state = replace(market_state)
        setattr(updated_state, "extreme_current_session", session)
        setattr(updated_state, "extreme_required_session", self.required_session)
        setattr(updated_state, "extreme_session_signal", session_signal)
        setattr(updated_state, "extreme_velocity_threshold", self.velocity_threshold)
        setattr(updated_state, "extreme_price_velocity", price_velocity)
        setattr(updated_state, "extreme_price_velocity_direction", velocity_direction)
        setattr(updated_state, "extreme_velocity_spike_signal", velocity_spike_signal)
        setattr(updated_state, "extreme_compression_signal", compression_signal)
        setattr(updated_state, "extreme_signal_detected", signal_detected)
        setattr(updated_state, "extreme_signal_strength", signal_strength)
        setattr(updated_state, "extreme_expected_direction", EXTREME_EXPECTED_DIRECTION)
        setattr(updated_state, "extreme_entry_direction", EXTREME_EXPECTED_DIRECTION if signal_detected else "N/A")
        setattr(updated_state, "extreme_lead_time_warning", "yes")
        setattr(updated_state, "extreme_max_holding_seconds", EXTREME_MAX_HOLDING_SECONDS)
        setattr(updated_state, "extreme_samples", len(self._prices))
        setattr(updated_state, "extreme_previous_price", previous_price)
        setattr(updated_state, "extreme_price_buffer_unique_values", len(set(self._prices)))
        setattr(updated_state, "extreme_pre_signal_unique_values", pre_unique_values)
        setattr(updated_state, "extreme_flat_samples_count", pre_flat_samples)
        setattr(updated_state, "extreme_compression_score", self._compression_score(pre_unique_values, pre_flat_samples))
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

    def _flat_samples_count(self, price: float | None) -> int:
        if price is None:
            return 0
        count = 0
        for item in reversed(self._prices):
            if item != price:
                break
            count += 1
        return count

    @staticmethod
    def _compression_score(unique_values: int, flat_samples: int) -> float:
        if unique_values <= 0:
            return 0.0
        unique_score = max(0.0, min(100.0, (EXTREME_COMPRESSION_MAX_UNIQUE_VALUES / unique_values) * 50.0))
        flat_score = max(0.0, min(50.0, (flat_samples / EXTREME_COMPRESSION_MIN_FLAT_SAMPLES) * 50.0))
        return min(100.0, unique_score + flat_score)

    def _signal_strength(
        self,
        *,
        session_signal: bool,
        velocity_spike_signal: bool,
        compression_signal: bool,
        price_velocity: float,
    ) -> float:
        score = 0.0
        if session_signal:
            score += 30.0
        if velocity_spike_signal:
            score += min(40.0, abs(price_velocity) / abs(self.velocity_threshold) * 20.0)
        if compression_signal:
            score += 30.0
        return min(100.0, score)
