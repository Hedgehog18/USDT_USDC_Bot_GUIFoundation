from market.binance_market_data_provider import BinanceMarketDataError
from market.market_analyzer import MarketAnalyzer


class FailingProvider:
    def get_bid_ask(self, symbol: str):
        raise BinanceMarketDataError("binance unavailable")


def test_market_analyzer_records_fallback_source_and_notifies(test_config):
    events = []
    analyzer = MarketAnalyzer(
        symbol=test_config.symbol,
        provider=FailingProvider(),
        use_real_data=True,
        config=test_config,
        fallback_callback=events.append,
    )

    state = analyzer.analyze_market()

    assert state.symbol == test_config.symbol
    assert analyzer.last_data_source == "FALLBACK"
    assert analyzer.last_fallback_error == "binance unavailable"
    assert events == ["binance unavailable"]


def test_market_analyzer_records_mock_source_when_real_data_disabled(test_config):
    analyzer = MarketAnalyzer(
        symbol=test_config.symbol,
        use_real_data=False,
        config=test_config,
    )

    analyzer.analyze_market()

    assert analyzer.last_data_source == "MOCK"
    assert analyzer.last_fallback_error == ""
