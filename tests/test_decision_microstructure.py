from datetime import datetime

from market.models import MarketState
from strategy.decision_engine import DecisionEngine


def make_state(**overrides):
    data = dict(
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
        order_book_imbalance=0.5,
        order_book_pressure="BID_PRESSURE",
        trade_volume_delta=0.5,
        micro_trend="BUY_DOMINANT",
        relative_volatility=0.0001,
        volatility_regime="NORMAL",
        created_at=datetime.utcnow(),
    )
    data.update(overrides)
    return MarketState(**data)


def test_decision_uses_supportive_buy_microstructure(test_config):
    state = make_state()
    decision = DecisionEngine(test_config).make_decision(state)

    assert decision.action == "BUY_USDC"
    assert "microstructure" in decision.reason


def test_decision_safe_wait_on_extreme_volatility(test_config):
    state = make_state(volatility_regime="EXTREME")
    decision = DecisionEngine(test_config).make_decision(state)

    assert decision.action == "SAFE_WAIT"


def test_opposite_microstructure_lowers_score(test_config):
    supportive = make_state()
    opposite = make_state(
        order_book_pressure="ASK_PRESSURE",
        micro_trend="SELL_DOMINANT",
    )

    engine = DecisionEngine(test_config)
    supportive_decision = engine.make_decision(supportive)
    opposite_decision = engine.make_decision(opposite)

    assert opposite_decision.cycle_prediction_score < supportive_decision.cycle_prediction_score
