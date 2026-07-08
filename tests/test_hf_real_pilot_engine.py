from dataclasses import replace
from decimal import Decimal

from analytics.hf_real_dry_run_engine import AccountBalances, ExchangeSymbolRules
from analytics.hf_real_pilot_engine import HFRealPilotEngine, RealOrderResult
from market.binance_market_data_provider import BidAsk
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


class FakeRealPilotClient:
    def __init__(
        self,
        *,
        usdt: Decimal = Decimal("20"),
        usdc: Decimal = Decimal("20"),
        order_status: str = "FILLED",
        permissions: dict | None = None,
    ) -> None:
        self.usdt = usdt
        self.usdc = usdc
        self.order_status = order_status
        self.orders_created = 0
        self.permissions = permissions or {
            "canTrade": True,
            "canWithdraw": False,
            "accountType": "SPOT",
            "permissions": ["SPOT"],
        }

    def get_bid_ask(self, symbol: str) -> BidAsk:
        return BidAsk(bid=1.00068, ask=1.00069)

    def get_symbol_rules(self, symbol: str) -> ExchangeSymbolRules:
        return ExchangeSymbolRules(
            symbol=symbol,
            status="TRADING",
            base_asset="USDC",
            quote_asset="USDT",
            base_precision=8,
            quote_precision=8,
            min_qty=Decimal("1"),
            step_size=Decimal("1"),
            min_notional=Decimal("5"),
            tick_size=Decimal("0.00001"),
        )

    def get_account_balances(self) -> AccountBalances:
        return AccountBalances(usdt=self.usdt, usdc=self.usdc)

    def get_account_permissions(self) -> dict:
        return dict(self.permissions)

    def create_market_order(self, *, symbol: str, side: str, quantity: Decimal) -> RealOrderResult:
        self.orders_created += 1
        return RealOrderResult(
            order_id="mock-order-1",
            status=self.order_status,
            executed_qty=quantity if self.order_status == "FILLED" else Decimal("0"),
            avg_price=Decimal("1.00069") if self.order_status == "FILLED" else Decimal("0"),
            raw_response={"orderId": "mock-order-1", "status": self.order_status, "side": side},
        )


def _config(test_config):
    return replace(test_config, symbol="USDCUSDT", mode="DEMO", max_allowed_spread=0.0002)


def _engine(tmp_path, test_config, client=None):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    return HFRealPilotEngine(
        database,
        _config(test_config),
        client or FakeRealPilotClient(),
        emergency_stop_path=tmp_path / "EMERGENCY_STOP",
    ), database


def test_real_pilot_refuses_without_explicit_confirmation(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=False)

    assert report.status == "REFUSED"
    assert client.orders_created == 0
    assert "explicit_confirmation" in {check.name for check in report.failed_checks}


def test_real_pilot_refuses_if_dry_run_not_ready(test_config, tmp_path):
    client = FakeRealPilotClient(usdt=Decimal("3"), usdc=Decimal("3"))
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)

    assert report.status == "NOT_READY"
    assert report.dry_run_status == "NOT_READY"
    assert client.orders_created == 0


def test_real_pilot_refuses_wrong_profile(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.run_once(profile="strict_current", pilot_stake=Decimal("6"), confirmed=True)

    assert report.status == "REFUSED"
    assert client.orders_created == 0
    assert "profile_allowed" in {check.name for check in report.failed_checks}


def test_real_pilot_max_one_open_real_cycle(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    database.save_real_pilot_cycle(
        run_id="existing",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)

    assert report.status == "NOT_READY"
    assert client.orders_created == 0
    assert "max_one_open_real_cycle" in {check.name for check in report.failed_checks}


def test_real_pilot_daily_loss_stop(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    cycle_id = database.save_real_pilot_cycle(
        run_id="loss-run",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )
    with database.connect() as conn:
        conn.execute(
            "UPDATE real_pilot_cycles SET status = 'CLOSED', net_profit = -2.0 WHERE id = ?",
            (cycle_id,),
        )
        conn.commit()

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)

    assert report.status == "NOT_READY"
    assert "daily_loss_limit" in {check.name for check in report.failed_checks}


def test_real_pilot_max_consecutive_losses_stop(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    for index in range(3):
        cycle_id = database.save_real_pilot_cycle(
            run_id=f"loss-run-{index}",
            strategy_profile=PROFILE,
            symbol="USDCUSDT",
            direction="BUY_USDC",
            status="OPEN",
            open_price=1.00068,
            quantity=6,
            stake_usdt=6,
        )
        with database.connect() as conn:
            conn.execute(
                "UPDATE real_pilot_cycles SET status = 'CLOSED', net_profit = -0.1 WHERE id = ?",
                (cycle_id,),
            )
            conn.commit()

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)

    assert report.status == "NOT_READY"
    assert "max_consecutive_losses" in {check.name for check in report.failed_checks}


def test_real_pilot_emergency_stop_blocks(test_config, tmp_path):
    client = FakeRealPilotClient()
    stop_path = tmp_path / "EMERGENCY_STOP"
    stop_path.write_text("stop", encoding="utf-8")
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = HFRealPilotEngine(database, _config(test_config), client, emergency_stop_path=stop_path)

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)

    assert report.status == "NOT_READY"
    assert client.orders_created == 0
    assert "emergency_stop_clear" in {check.name for check in report.failed_checks}


def test_real_pilot_order_client_mocked_and_no_paper_contamination(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)

    report = engine.run_once(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        entry_signal="BUY_USDC",
    )

    assert report.status == "ORDER_PLACED"
    assert report.real_cycle_id is not None
    assert client.orders_created == 1
    assert database.count_open_real_pilot_cycles(PROFILE) == 1
    with database.connect() as conn:
        paper_count = conn.execute("SELECT COUNT(*) FROM paper_cycles").fetchone()[0]
    assert paper_count == 0


def test_real_pilot_status_reads_isolated_real_tables(test_config, tmp_path):
    engine, database = _engine(tmp_path, test_config)
    database.save_real_pilot_cycle(
        run_id="status",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="SELL_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )

    report = engine.build_status(PROFILE)

    assert report.status == "OPEN_REAL_CYCLE"
    assert report.open_cycles == 1
