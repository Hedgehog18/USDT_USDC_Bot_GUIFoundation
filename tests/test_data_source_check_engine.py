from market.binance_market_data_provider import BidAsk, BinanceMarketDataError
from analytics.data_source_check_engine import DataSourceCheckEngine


class WorkingProvider:
    def get_bid_ask(self, symbol: str) -> BidAsk:
        return BidAsk(bid=1.0, ask=1.0002)


class FailingProvider:
    def get_bid_ask(self, symbol: str) -> BidAsk:
        raise BinanceMarketDataError("network unavailable")


def test_data_source_check_reports_binance_when_real_data_is_enabled(test_config):
    config = test_config.__class__(
        **{
            **test_config.__dict__,
            "use_real_market_data": True,
        }
    )
    report = DataSourceCheckEngine(config, provider=WorkingProvider()).build_report()

    assert report.mode == config.mode
    assert report.use_real_market_data is True
    assert report.binance_ok is True
    assert report.last_price == 1.0001
    assert report.timestamp is not None
    assert report.source == "BINANCE"
    assert report.backtest_source == "BINANCE"
    assert report.runner_source == "BINANCE"


def test_data_source_check_reports_fallback_when_binance_fails(test_config):
    config = test_config.__class__(
        **{
            **test_config.__dict__,
            "use_real_market_data": True,
        }
    )

    report = DataSourceCheckEngine(config, provider=FailingProvider()).build_report()

    assert report.binance_ok is False
    assert report.last_price is None
    assert report.timestamp is None
    assert report.source == "FALLBACK"
    assert report.error_message == "network unavailable"
