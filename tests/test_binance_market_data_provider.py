from market.binance_market_data_provider import BinanceMarketDataProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_provider_parses_bid_ask(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse({"bidPrice": "0.99999", "askPrice": "1.00001"})

    monkeypatch.setattr("requests.get", fake_get)

    provider = BinanceMarketDataProvider()
    bid_ask = provider.get_bid_ask("USDCUSDT")

    assert bid_ask.bid == 0.99999
    assert bid_ask.ask == 1.00001


def test_provider_parses_kline_closes(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse([
            [1, "0", "0", "0", "1.00000"],
            [2, "0", "0", "0", "1.00001"],
        ])

    monkeypatch.setattr("requests.get", fake_get)

    provider = BinanceMarketDataProvider()
    closes = provider.get_kline_closes("USDCUSDT", "1m", 2)

    assert closes.closes == [1.0, 1.00001]
