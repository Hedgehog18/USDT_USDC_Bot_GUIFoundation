from market.binance_market_data_provider import BinanceMarketDataProvider
from market.market_data_cache import MarketDataCache


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_provider_uses_cache_for_bid_ask(monkeypatch):
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return FakeResponse({"bidPrice": "0.99999", "askPrice": "1.00001"})

    monkeypatch.setattr("requests.get", fake_get)

    provider = BinanceMarketDataProvider(cache=MarketDataCache(ttl_seconds=5))
    first = provider.get_bid_ask("USDCUSDT")
    second = provider.get_bid_ask("USDCUSDT")

    assert first == second
    assert calls["count"] == 1


def test_provider_uses_cache_for_klines(monkeypatch):
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return FakeResponse([
            [1, "0", "0", "0", "1.00000"],
            [2, "0", "0", "0", "1.00001"],
        ])

    monkeypatch.setattr("requests.get", fake_get)

    provider = BinanceMarketDataProvider(cache=MarketDataCache(ttl_seconds=5))
    first = provider.get_kline_closes("USDCUSDT", "1m", 2)
    second = provider.get_kline_closes("USDCUSDT", "1m", 2)

    assert first == second
    assert calls["count"] == 1
