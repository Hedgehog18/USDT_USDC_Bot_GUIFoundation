from dataclasses import replace
from datetime import datetime, timedelta

from analytics.hf_production_readiness_engine import HFProductionReadinessEngine
from market.binance_market_data_provider import BidAsk, BinanceMarketDataError, OrderBookData
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


class FakeMarketProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def get_bid_ask(self, symbol: str) -> BidAsk:
        if self.fail:
            raise BinanceMarketDataError("Binance unavailable")
        return BidAsk(bid=1.0001, ask=1.0002)

    def get_order_book(self, symbol: str, limit: int = 20) -> OrderBookData:
        if self.fail:
            raise BinanceMarketDataError("Binance unavailable")
        return OrderBookData(bids=[(1.0001, 100.0)], asks=[(1.0002, 100.0)])


def _config(test_config, tmp_path, *, mode: str = "DEMO"):
    return replace(
        test_config,
        mode=mode,
        database_path=str(tmp_path / "bot.sqlite"),
        log_file_path=str(tmp_path / "logs" / "bot.log"),
        use_real_market_data=True,
    )


def _insert_cycle(
    database: DatabaseManager,
    *,
    status: str = "CLOSED",
    net_profit: float = 0.01,
    profile: str = PROFILE,
) -> None:
    opened_at = datetime(2026, 7, 1, 12, 0, 0)
    closed_at = opened_at + timedelta(minutes=1) if status != "OPEN" else None
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (closed_at or opened_at).isoformat(),
                1,
                profile,
                "BUY_USDC",
                status,
                1.0,
                1.0001,
                10.0,
                0.0,
                0.0,
                net_profit,
                net_profit,
                opened_at.isoformat(),
                closed_at.isoformat() if closed_at else None,
                "target" if status != "OPEN" else None,
            ),
        )
        conn.commit()


def test_hf_production_readiness_passes_with_mocked_clean_state(test_config, tmp_path):
    config = _config(test_config, tmp_path)
    database = DatabaseManager(config.database_path)
    _insert_cycle(database)

    report = HFProductionReadinessEngine(database, config, FakeMarketProvider()).build_report(PROFILE)

    assert report.status == "READY_FOR_DRY_RUN"
    assert report.ready is True
    assert all(check.ok for check in report.checks)


def test_hf_production_readiness_fails_with_open_cycles(test_config, tmp_path):
    config = _config(test_config, tmp_path)
    database = DatabaseManager(config.database_path)
    _insert_cycle(database)
    _insert_cycle(database, status="OPEN", net_profit=0.0)

    report = HFProductionReadinessEngine(database, config, FakeMarketProvider()).build_report(PROFILE)

    assert report.status == "NOT_READY"
    failed = {check.name for check in report.failed_checks}
    assert "no_open_paper_cycles" in failed
    assert "recovery_state_clean" in failed


def test_hf_production_readiness_fails_if_binance_unavailable(test_config, tmp_path):
    config = _config(test_config, tmp_path)
    database = DatabaseManager(config.database_path)
    _insert_cycle(database)

    report = HFProductionReadinessEngine(database, config, FakeMarketProvider(fail=True)).build_report(PROFILE)

    failed = {check.name for check in report.failed_checks}
    assert report.status == "NOT_READY"
    assert "binance_connection" in failed
    assert "symbol_precision_min_notional" in failed


def test_hf_production_readiness_confirms_real_trading_disabled(test_config, tmp_path):
    config = _config(test_config, tmp_path, mode="DEMO")
    database = DatabaseManager(config.database_path)
    _insert_cycle(database)

    report = HFProductionReadinessEngine(database, config, FakeMarketProvider()).build_report(PROFILE)

    check = next(item for item in report.checks if item.name == "real_trading_disabled")
    assert check.ok is True
    assert "DEMO" in check.message


def test_hf_production_readiness_fails_when_real_mode_enabled(test_config, tmp_path):
    config = _config(test_config, tmp_path, mode="REAL")
    database = DatabaseManager(config.database_path)
    _insert_cycle(database)

    report = HFProductionReadinessEngine(database, config, FakeMarketProvider()).build_report(PROFILE)

    check = next(item for item in report.checks if item.name == "real_trading_disabled")
    assert check.ok is False
    assert report.status == "NOT_READY"
