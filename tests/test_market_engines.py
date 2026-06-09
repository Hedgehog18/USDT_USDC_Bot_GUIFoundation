from market.binance_market_data_provider import OrderBookData, RecentTradeData
from market.order_book_engine import OrderBookEngine
from market.trade_history_engine import TradeHistoryEngine
from market.volatility_engine import VolatilityEngine


def test_order_book_engine_detects_bid_pressure():
    order_book = OrderBookData(
        bids=[(1.0, 10.0), (0.9999, 10.0)],
        asks=[(1.0001, 2.0), (1.0002, 2.0)],
    )
    metrics = OrderBookEngine().analyze(order_book)

    assert metrics.pressure == "BID_PRESSURE"
    assert metrics.imbalance > 0


def test_trade_history_engine_detects_buy_dominant():
    trades = [
        RecentTradeData(price=1.0, quantity=10.0, is_buyer_maker=False),
        RecentTradeData(price=1.0, quantity=5.0, is_buyer_maker=False),
        RecentTradeData(price=1.0, quantity=1.0, is_buyer_maker=True),
    ]
    metrics = TradeHistoryEngine().analyze(trades)

    assert metrics.micro_trend == "BUY_DOMINANT"
    assert metrics.volume_delta > 0


def test_volatility_engine_returns_regime():
    prices = [1.0, 1.0001, 0.9999, 1.0002, 0.9998]
    metrics = VolatilityEngine().analyze(prices)

    assert metrics.relative_volatility > 0
    assert metrics.volatility_regime in {"LOW", "NORMAL", "HIGH", "EXTREME"}
