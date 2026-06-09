from market.market_health_engine import MarketHealthEngine
from market.order_book_engine import OrderBookMetrics


def make_order_book_metrics(liquidity_score=20.0, pressure="BALANCED"):
    return OrderBookMetrics(
        bid_volume=10.0,
        ask_volume=10.0,
        imbalance=0.0,
        best_bid=0.99999,
        best_ask=1.00001,
        spread=0.00002,
        liquidity_score=liquidity_score,
        pressure=pressure,
    )


def test_market_health_healthy(test_config):
    engine = MarketHealthEngine(test_config)
    health = engine.analyze(
        spread=0.00001,
        volatility_regime="NORMAL",
        order_book_metrics=make_order_book_metrics(),
    )

    assert health.status == "HEALTHY"
    assert health.score >= 75


def test_market_health_unhealthy_on_large_spread(test_config):
    engine = MarketHealthEngine(test_config)
    health = engine.analyze(
        spread=0.001,
        volatility_regime="NORMAL",
        order_book_metrics=make_order_book_metrics(),
    )

    assert health.status in {"CAUTION", "UNHEALTHY"}
    assert health.score < 100


def test_market_health_unhealthy_on_extreme_volatility(test_config):
    engine = MarketHealthEngine(test_config)
    health = engine.analyze(
        spread=0.00001,
        volatility_regime="EXTREME",
        order_book_metrics=make_order_book_metrics(),
    )

    assert health.status == "UNHEALTHY"
