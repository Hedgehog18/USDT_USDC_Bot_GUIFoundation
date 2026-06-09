from datetime import datetime

from market.models import MarketState
from strategy.decision_engine import DecisionEngine


def test_decision_safe_wait_when_market_unhealthy(test_config):
    state = MarketState(
        symbol="USDCUSDT",
        price=1.0,
        bid=0.99999,
        ask=1.00001,
        spread=0.00002,
        work_low=0.9999,
        work_high=1.0001,
        work_center=1.0,
        work_position=10.0,
        short_low=0.9998,
        short_high=1.0002,
        short_center=1.0,
        short_position=20.0,
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
        relative_volatility=0.001,
        volatility_regime="EXTREME",
        market_health_score=20.0,
        market_health_status="UNHEALTHY",
        market_health_reason="Екстремальна волатильність",
        created_at=datetime.utcnow(),
    )

    decision = DecisionEngine(test_config).make_decision(state)

    assert decision.action == "SAFE_WAIT"
