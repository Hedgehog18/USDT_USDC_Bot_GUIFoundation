from datetime import datetime

from market.models import MarketState
from paper.hf_short_center_provider import HFShortCenterMarketAnalyzer


class SequenceAnalyzer:
    def __init__(self, prices: list[float]):
        self.prices = list(prices)
        self.index = 0
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
            created_at=datetime.utcnow(),
        )


def test_hf_short_center_not_ready_before_min_samples():
    provider = HFShortCenterMarketAnalyzer(SequenceAnalyzer([1.0, 1.0001]), min_samples=3, window=10)

    first = provider.analyze_market()
    second = provider.analyze_market()

    assert first.short_center == 0.0
    assert first.hf_short_center_samples == 1
    assert first.hf_short_center_ready is False
    assert second.short_center == 0.0
    assert second.hf_short_center_samples == 2
    assert second.hf_short_center_ready is False


def test_hf_short_center_ready_at_min_samples():
    provider = HFShortCenterMarketAnalyzer(SequenceAnalyzer([1.0, 1.0001, 1.0002]), min_samples=3, window=10)

    provider.analyze_market()
    provider.analyze_market()
    third = provider.analyze_market()

    assert third.short_center == 1.0001
    assert third.hf_short_center_samples == 3
    assert third.hf_short_center_ready is True


def test_hf_short_center_tracks_last_different_price_and_flat_buffer():
    provider = HFShortCenterMarketAnalyzer(
        SequenceAnalyzer([1.0, 1.0, 1.0001, 1.0001]),
        min_samples=3,
        window=10,
    )

    provider.analyze_market()
    second = provider.analyze_market()
    third = provider.analyze_market()
    fourth = provider.analyze_market()

    assert second.hf_previous_price == 1.0
    assert second.hf_last_different_price is None
    assert second.hf_price_buffer_unique_values == 1
    assert second.hf_flat_samples_count == 2
    assert second.hf_flat_price_buffer is True
    assert third.hf_last_different_price == 1.0
    assert third.hf_price_buffer_unique_values == 2
    assert third.hf_flat_price_buffer is False
    assert fourth.hf_previous_price == 1.0001
    assert fourth.hf_last_different_price == 1.0
    assert fourth.hf_flat_samples_count == 2
