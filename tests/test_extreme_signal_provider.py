from datetime import datetime

from market.models import MarketState
from paper.extreme_signal_provider import ExtremeSignalMarketAnalyzer


class ExtremeSequenceAnalyzer:
    def __init__(self, prices: list[float], *, hour: int = 18):
        self.prices = list(prices)
        self.index = 0
        self.hour = hour
        self.last_data_source = "TEST"

    def analyze_market(self):
        price = self.prices[min(self.index, len(self.prices) - 1)]
        self.index += 1
        return MarketState(
            symbol="USDCUSDT",
            price=price,
            bid=price - 0.00001,
            ask=price + 0.00001,
            spread=0.00002,
            work_low=0.9999,
            work_high=1.0001,
            work_center=1.0,
            work_position=50.0,
            short_low=0.0,
            short_high=0.0,
            short_center=0.0,
            short_position=50.0,
            long_low=0.9995,
            long_high=1.0005,
            long_center=1.0,
            long_position=50.0,
            center_confidence="HIGH",
            center_alignment="FLAT",
            tick_activity_score=80.0,
            center_crossing_score=80.0,
            mean_reversion_score=80.0,
            spread_stability_score=90.0,
            corridor_quality_score=80.0,
            market_activity_score=80.0,
            market_regime="ACTIVE",
            order_book_imbalance=0.0,
            order_book_pressure="BALANCED",
            trade_volume_delta=0.0,
            micro_trend="NEUTRAL",
            relative_volatility=0.0,
            volatility_regime="NORMAL",
            market_health_score=100.0,
            market_health_status="HEALTHY",
            market_health_reason="test",
            created_at=datetime(2026, 7, 2, self.hour, 0, self.index),
        )


def test_extreme_signal_detects_session_velocity_and_compression():
    provider = ExtremeSignalMarketAnalyzer(ExtremeSequenceAnalyzer(([1.0000] * 5) + [0.999998]))

    for _ in range(5):
        provider.analyze_market()
    signal = provider.analyze_market()

    assert signal.extreme_signal_detected is True
    assert signal.extreme_session_signal is True
    assert signal.extreme_velocity_spike_signal is True
    assert signal.extreme_compression_signal is True
    assert signal.extreme_entry_direction == "SELL_USDC"


def test_extreme_signal_requires_new_york_session():
    provider = ExtremeSignalMarketAnalyzer(ExtremeSequenceAnalyzer(([1.0000] * 5) + [0.999998], hour=3))

    for _ in range(5):
        provider.analyze_market()
    signal = provider.analyze_market()

    assert signal.extreme_signal_detected is False
    assert signal.extreme_session_signal is False


def test_extreme_signal_requires_velocity_spike():
    provider = ExtremeSignalMarketAnalyzer(ExtremeSequenceAnalyzer([1.0000] * 6))

    for _ in range(5):
        provider.analyze_market()
    signal = provider.analyze_market()

    assert signal.extreme_signal_detected is False
    assert signal.extreme_velocity_spike_signal is False


def test_extreme_signal_requires_compression():
    provider = ExtremeSignalMarketAnalyzer(
        ExtremeSequenceAnalyzer([1.0000, 1.0001, 1.0002, 1.0003, 1.0004, 1.000398])
    )

    for _ in range(5):
        provider.analyze_market()
    signal = provider.analyze_market()

    assert signal.extreme_signal_detected is False
    assert signal.extreme_compression_signal is False
