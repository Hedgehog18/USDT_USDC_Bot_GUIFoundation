from datetime import datetime

from market.models import MarketState
from strategy.profile_decision_engine import StrategyProfileDecisionEngine


def _state(**overrides):
    data = {
        "symbol": "USDCUSDT",
        "price": 1.0,
        "bid": 0.99999,
        "ask": 1.00001,
        "spread": 0.00002,
        "work_low": 0.9999,
        "work_high": 1.0001,
        "work_center": 1.0,
        "work_position": 10.0,
        "short_low": 0.9998,
        "short_high": 1.0002,
        "short_center": 1.0,
        "short_position": 50.0,
        "long_low": 0.9995,
        "long_high": 1.0005,
        "long_center": 1.0,
        "long_position": 50.0,
        "center_confidence": "LOW",
        "center_alignment": "MIXED",
        "tick_activity_score": 80.0,
        "center_crossing_score": 80.0,
        "mean_reversion_score": 80.0,
        "spread_stability_score": 90.0,
        "corridor_quality_score": 80.0,
        "market_activity_score": 80.0,
        "market_regime": "NORMAL",
        "order_book_imbalance": 0.0,
        "order_book_pressure": "BALANCED",
        "trade_volume_delta": 0.0,
        "micro_trend": "BUY_DOMINANT",
        "relative_volatility": 0.0,
        "volatility_regime": "LOW",
        "market_health_score": 100.0,
        "market_health_status": "HEALTHY",
        "market_health_reason": "test",
        "created_at": datetime.utcnow(),
    }
    data.update(overrides)
    return MarketState(**data)


def test_profile_decision_engine_strict_current_delegates_low_confidence(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "strict_current").make_decision(_state())

    assert decision.action == "WAIT"
    assert decision.reason == "Low center confidence"


def test_profile_decision_engine_mean_reversion_buy_candidate(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v1").make_decision(_state())

    assert decision.action == "BUY_USDC"
    assert decision.cycle_prediction_score >= test_config.min_cycle_prediction_score
    assert "mean_reversion_v1" in decision.reason


def test_profile_decision_engine_mean_reversion_requires_micro_trend(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v1").make_decision(
        _state(micro_trend="SELL_DOMINANT")
    )

    assert decision.action == "WAIT"
    assert "micro trend not confirmed" in decision.reason


def test_profile_decision_engine_mean_reversion_sell_candidate(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v1").make_decision(
        _state(work_position=85.0, micro_trend="SELL_DOMINANT")
    )

    assert decision.action == "SELL_USDC"


def test_profile_decision_engine_mean_reversion_v2_uses_calibrated_buy_zone(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v2").make_decision(
        _state(work_position=25.0, micro_trend="BUY_DOMINANT", order_book_pressure="ASK_PRESSURE")
    )

    assert decision.action == "BUY_USDC"
    assert "mean_reversion_v2" in decision.reason


def test_profile_decision_engine_mean_reversion_v2_uses_calibrated_sell_zone(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v2").make_decision(
        _state(work_position=75.0, micro_trend="SELL_DOMINANT", center_confidence="LOW")
    )

    assert decision.action == "SELL_USDC"
    assert "mean_reversion_v2" in decision.reason


def test_profile_decision_engine_mean_reversion_v2_keeps_strict_micro_trend(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v2").make_decision(
        _state(work_position=25.0, micro_trend="NEUTRAL")
    )

    assert decision.action == "WAIT"
    assert "micro trend not confirmed" in decision.reason


def test_profile_decision_engine_mean_reversion_v2_small_target_uses_v2_entry_rules(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_v2_small_target").make_decision(
        _state(work_position=25.0, micro_trend="BUY_DOMINANT", center_confidence="LOW")
    )

    assert decision.action == "BUY_USDC"
    assert "mean_reversion_v2_small_target" in decision.reason
    assert decision.target_profit == test_config.target_profit * 0.25


def test_profile_decision_engine_hf_micro_buy_when_price_below_short_center(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        _state(price=1.000005, short_center=1.0001, work_position=50.0, micro_trend="NEUTRAL")
    )

    assert decision.action == "BUY_USDC"
    assert "mean_reversion_hf_micro_v1" in decision.reason
    assert decision.target_profit == 0.000005


def test_profile_decision_engine_hf_micro_sell_when_price_above_short_center(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        _state(price=1.000005, short_center=1.0, work_position=50.0, micro_trend="NEUTRAL")
    )

    assert decision.action == "SELL_USDC"
    assert decision.target_profit == 0.000005


def test_profile_decision_engine_hf_micro_waits_when_price_equals_short_center(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        _state(price=1.000005, short_center=1.000005)
    )

    assert decision.action == "WAIT"
    assert "price_equals_short_center" in decision.reason


def test_profile_decision_engine_hf_micro_fallback_sells_when_equal_center_and_last_different_lower(test_config):
    market_state = _state(price=1.000005, short_center=1.000005)
    setattr(market_state, "hf_last_different_price", 1.000000)
    setattr(market_state, "hf_flat_price_buffer", False)

    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        market_state
    )

    assert decision.action == "SELL_USDC"
    assert "equal_center_last_different_fallback" in decision.reason


def test_profile_decision_engine_hf_micro_fallback_buys_when_equal_center_and_last_different_higher(test_config):
    market_state = _state(price=1.000005, short_center=1.000005)
    setattr(market_state, "hf_last_different_price", 1.000010)
    setattr(market_state, "hf_flat_price_buffer", False)

    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        market_state
    )

    assert decision.action == "BUY_USDC"
    assert "equal_center_last_different_fallback" in decision.reason


def test_profile_decision_engine_hf_micro_waits_on_flat_price_buffer(test_config):
    market_state = _state(price=1.000005, short_center=1.000005)
    setattr(market_state, "hf_last_different_price", None)
    setattr(market_state, "hf_flat_price_buffer", True)

    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        market_state
    )

    assert decision.action == "WAIT"
    assert "flat_price_buffer" in decision.reason


def test_profile_decision_engine_hf_micro_waits_without_short_center(test_config):
    decision = StrategyProfileDecisionEngine(test_config, "mean_reversion_hf_micro_v1").make_decision(
        _state(price=1.000005, short_center=0.0)
    )

    assert decision.action == "WAIT"
    assert "no_short_center" in decision.reason


def test_profile_decision_engine_rejects_removed_experimental_profiles(test_config):
    for profile in [
        "mean_reversion_v2_small_target_ny",
        "mean_reversion_v2_small_target_tol1",
        "mean_reversion_v2_small_target_r7",
        "mean_reversion_v2_small_target_max12h",
    ]:
        try:
            StrategyProfileDecisionEngine(test_config, profile)
        except ValueError as exc:
            assert "Unsupported strategy profile" in str(exc)
        else:
            raise AssertionError(f"profile should be unsupported: {profile}")
