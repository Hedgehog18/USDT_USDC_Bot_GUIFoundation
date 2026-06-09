from market.binance_market_data_provider import BinanceMarketDataProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_provider_parses_order_book(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse({
            "bids": [["1.00000", "10"], ["0.99999", "5"]],
            "asks": [["1.00001", "4"], ["1.00002", "3"]],
        })

    monkeypatch.setattr("requests.get", fake_get)

    provider = BinanceMarketDataProvider()
    data = provider.get_order_book("USDCUSDT", 2)

    assert len(data.bids) == 2
    assert data.bids[0] == (1.0, 10.0)


def test_provider_parses_recent_trades(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse([
            {"price": "1.00000", "qty": "10", "isBuyerMaker": False},
            {"price": "1.00001", "qty": "5", "isBuyerMaker": True},
        ])

    monkeypatch.setattr("requests.get", fake_get)

    provider = BinanceMarketDataProvider()
    data = provider.get_recent_trades("USDCUSDT", 2)

    assert len(data) == 2
    assert data[0].quantity == 10.0
