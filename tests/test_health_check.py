from dataclasses import replace
from pathlib import Path

from health.health_check import HealthCheck
from market.binance_market_data_provider import BidAsk
from storage.database_manager import DatabaseManager


class FakeProvider:
    def get_bid_ask(self, symbol: str) -> BidAsk:
        return BidAsk(bid=0.99999, ask=1.00001)


class BadProvider:
    def get_bid_ask(self, symbol: str) -> BidAsk:
        return BidAsk(bid=0.0, ask=0.0)


def test_health_check_ok(test_config, tmp_path: Path):
    config = replace(
        test_config,
        database_path=str(tmp_path / "bot.sqlite"),
        use_real_market_data=True,
    )
    database = DatabaseManager(config.database_path)

    report = HealthCheck(
        config=config,
        database=database,
        market_provider=FakeProvider(),
    ).run()

    assert report.ok is True


def test_health_check_bad_config(test_config, tmp_path: Path):
    config = replace(
        test_config,
        database_path=str(tmp_path / "bot.sqlite"),
        trade_size_percent=2.0,
    )
    database = DatabaseManager(config.database_path)

    report = HealthCheck(
        config=config,
        database=database,
        market_provider=FakeProvider(),
    ).run()

    assert report.ok is False
    assert any(item.name == "config" for item in report.failed_items)


def test_health_check_bad_provider(test_config, tmp_path: Path):
    config = replace(
        test_config,
        database_path=str(tmp_path / "bot.sqlite"),
        use_real_market_data=True,
    )
    database = DatabaseManager(config.database_path)

    report = HealthCheck(
        config=config,
        database=database,
        market_provider=BadProvider(),
    ).run()

    assert report.ok is False
    assert any(item.name == "binance_read_only" for item in report.failed_items)
