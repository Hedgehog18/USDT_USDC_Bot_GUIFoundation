from datetime import datetime

from analytics.entry_zone_debug_report import EntryZoneDebugReportBuilder
from market.models import MarketState


def _state(work_position: float, micro_trend: str = "NEUTRAL") -> MarketState:
    return MarketState(
        symbol="USDCUSDT",
        price=1.0,
        bid=0.99999,
        ask=1.00001,
        spread=0.00002,
        work_low=0.9998,
        work_high=1.0002,
        work_center=1.0,
        work_position=work_position,
        short_low=0.9998,
        short_high=1.0002,
        short_center=1.0,
        short_position=50.0,
        long_low=0.9995,
        long_high=1.0005,
        long_center=1.0,
        long_position=50.0,
        center_confidence="LOW",
        center_alignment="DIVERGED",
        tick_activity_score=50.0,
        center_crossing_score=50.0,
        mean_reversion_score=50.0,
        spread_stability_score=90.0,
        corridor_quality_score=80.0,
        market_activity_score=60.0,
        market_regime="NORMAL",
        order_book_imbalance=0.0,
        order_book_pressure="BALANCED",
        trade_volume_delta=0.0,
        micro_trend=micro_trend,
        relative_volatility=0.0,
        volatility_regime="LOW",
        market_health_score=100.0,
        market_health_status="HEALTHY",
        market_health_reason="test",
        created_at=datetime.utcnow(),
    )


def test_entry_zone_debug_report_builder_counts_iteration_outcomes(test_config):
    builder = EntryZoneDebugReportBuilder(test_config)

    builder.add({
        "index": 0,
        "market_state": _state(50.0),
        "action": "WAIT",
        "reason": "mean_reversion_v1: price outside entry zones",
        "risk_allowed": False,
        "risk_reason": "not needed",
        "risk_check_evaluated": False,
        "order_attempted": False,
        "data_source": "BINANCE",
    })
    builder.add({
        "index": 1,
        "market_state": _state(10.0, "SELL_DOMINANT"),
        "action": "WAIT",
        "reason": "mean_reversion_v1: BUY micro trend not confirmed",
        "risk_allowed": False,
        "risk_reason": "not needed",
        "risk_check_evaluated": False,
        "order_attempted": False,
        "data_source": "BINANCE",
    })
    builder.add({
        "index": 2,
        "market_state": _state(85.0, "SELL_DOMINANT"),
        "action": "SELL_USDC",
        "reason": "mean_reversion_v1: upper entry zone with SELL_DOMINANT micro trend",
        "risk_allowed": True,
        "risk_reason": "OK",
        "risk_check_evaluated": True,
        "order_attempted": True,
        "data_source": "BINANCE",
    })

    summary = builder.summary()

    assert summary.total_iterations == 3
    assert summary.buy_zone_active_count == 1
    assert summary.sell_zone_active_count == 1
    assert summary.no_zone_count == 1
    assert summary.blocked_by_micro_trend_count == 1
    assert summary.candidates_produced_count == 1
    assert summary.risk_checks_evaluated_count == 1
    assert summary.orders_attempted_count == 1


def test_entry_zone_debug_report_builder_explains_reference_deviation(test_config):
    builder = EntryZoneDebugReportBuilder(test_config)
    item = builder.add({
        "index": 0,
        "market_state": _state(50.0),
        "action": "WAIT",
        "reason": "mean_reversion_v1: price outside entry zones",
        "risk_allowed": False,
        "risk_reason": "not needed",
        "risk_check_evaluated": False,
        "order_attempted": False,
        "data_source": "BINANCE",
    })

    assert item.reference_price == 1.0
    assert item.deviation_from_mean == 0.0
    assert item.buy_zone_threshold == test_config.buy_zone_max
    assert item.sell_zone_threshold == test_config.sell_zone_min
