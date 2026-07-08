from dataclasses import replace
from decimal import Decimal

from analytics.hf_real_dry_run_engine import (
    AccountBalances,
    ExchangeSymbolRules,
    HFRealDryRunEngine,
)
from market.binance_market_data_provider import BidAsk, BinanceMarketDataError


PROFILE = "mean_reversion_hf_micro_v1"


class FakeRealDryRunProvider:
    def __init__(
        self,
        *,
        symbol_available: bool = True,
        usdt: Decimal = Decimal("100"),
        usdc: Decimal = Decimal("100"),
        price: float = 1.00067,
        min_notional: Decimal = Decimal("5"),
    ) -> None:
        self.symbol_available = symbol_available
        self.usdt = usdt
        self.usdc = usdc
        self.price = price
        self.min_notional = min_notional
        self.orders_created = 0

    def get_bid_ask(self, symbol: str) -> BidAsk:
        return BidAsk(bid=self.price, ask=self.price + 0.00001)

    def get_symbol_rules(self, symbol: str) -> ExchangeSymbolRules:
        if not self.symbol_available:
            raise BinanceMarketDataError("Symbol unavailable")
        return ExchangeSymbolRules(
            symbol=symbol,
            status="TRADING",
            base_asset="USDC",
            quote_asset="USDT",
            base_precision=8,
            quote_precision=8,
            min_qty=Decimal("0.1"),
            step_size=Decimal("0.0001"),
            min_notional=self.min_notional,
            tick_size=Decimal("0.00001"),
        )

    def get_account_balances(self) -> AccountBalances:
        return AccountBalances(usdt=self.usdt, usdc=self.usdc)


def _config(test_config, *, mode: str = "DEMO", trade_size_percent: float = 0.10):
    return replace(
        test_config,
        mode=mode,
        symbol="USDCUSDT",
        use_real_market_data=True,
        trade_size_percent=trade_size_percent,
    )


def test_hf_real_dry_run_ready_with_clean_mocked_exchange(test_config):
    provider = FakeRealDryRunProvider()
    report = HFRealDryRunEngine(_config(test_config), provider).build_report(PROFILE)

    assert report.status == "READY_FOR_SMALL_REAL_PILOT"
    assert report.ready is True
    assert all(check.ok for check in report.checks)


def test_hf_real_dry_run_fails_if_symbol_unavailable(test_config):
    provider = FakeRealDryRunProvider(symbol_available=False)
    report = HFRealDryRunEngine(_config(test_config), provider).build_report(PROFILE)

    assert report.status == "NOT_READY"
    assert "symbol_rules_readable" in {check.name for check in report.failed_checks}


def test_hf_real_dry_run_fails_if_stake_below_min_notional(test_config):
    provider = FakeRealDryRunProvider(usdt=Decimal("10"), usdc=Decimal("10"), min_notional=Decimal("5"))
    report = HFRealDryRunEngine(_config(test_config, trade_size_percent=0.10), provider).build_report(PROFILE)

    failed = {check.name for check in report.failed_checks}
    assert report.status == "NOT_READY"
    assert "proposed_stake_min_notional" in failed


def test_hf_real_dry_run_confirms_no_order_creation(test_config):
    provider = FakeRealDryRunProvider()
    report = HFRealDryRunEngine(_config(test_config), provider).build_report(PROFILE)

    check = next(item for item in report.checks if item.name == "no_orders_created")
    assert check.ok is True
    assert provider.orders_created == 0


def test_hf_real_dry_run_fails_if_real_trading_enabled_unexpectedly(test_config):
    provider = FakeRealDryRunProvider()
    report = HFRealDryRunEngine(_config(test_config, mode="REAL"), provider).build_report(PROFILE)

    check = next(item for item in report.checks if item.name == "real_trading_disabled")
    assert check.ok is False
    assert report.status == "NOT_READY"


def test_hf_real_dry_run_output_recommendation_not_ready(test_config):
    provider = FakeRealDryRunProvider(usdt=Decimal("0"), usdc=Decimal("0"))
    report = HFRealDryRunEngine(_config(test_config), provider).build_report(PROFILE)

    assert report.status == "NOT_READY"
    assert report.ready is False
