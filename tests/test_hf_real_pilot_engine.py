from dataclasses import replace
from decimal import Decimal

from analytics.hf_real_dry_run_engine import AccountBalances, ExchangeSymbolRules
from analytics.hf_real_pilot_engine import HFRealPilotEngine, HFRealPilotSignalSnapshot, RealOrderResult
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
        bid: float = 1.00068,
        ask: float = 1.00069,
        order_avg_price: Decimal = Decimal("1.00069"),
    ) -> None:
        self.usdt = usdt
        self.usdc = usdc
        self.order_status = order_status
        self.orders_created = 0
        self.bid = bid
        self.ask = ask
        self.order_avg_price = order_avg_price
        self.permissions = permissions or {
            "canTrade": True,
            "canWithdraw": False,
            "accountType": "SPOT",
            "permissions": ["SPOT"],
        }

    def get_bid_ask(self, symbol: str) -> BidAsk:
        return BidAsk(bid=self.bid, ask=self.ask)

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
            avg_price=self.order_avg_price if self.order_status == "FILLED" else Decimal("0"),
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


def test_real_pilot_does_not_block_on_account_level_can_withdraw(test_config, tmp_path):
    client = FakeRealPilotClient(permissions={
        "canTrade": True,
        "canWithdraw": True,
        "accountType": "SPOT",
        "permissions": ["SPOT"],
    })
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)

    permission_check = next(check for check in report.checks if check.name == "api_permissions_spot_only")
    assert permission_check.ok is True
    assert "account-level" in permission_check.message
    assert report.status == "ARMED_WAITING_FOR_SIGNAL"
    assert client.orders_created == 0


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


def _watch_signal(entry_signal: str | None = None) -> HFRealPilotSignalSnapshot:
    return HFRealPilotSignalSnapshot(
        price=1.00068,
        short_center=1.00070,
        hf_entry_mode="short_center",
        candidate=entry_signal is not None,
        entry_signal=entry_signal,
        block_reason="no_signal" if entry_signal is None else "N/A",
    )


def test_real_pilot_watch_refuses_without_confirmation(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.watch(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=False,
        max_iterations=5,
        interval_seconds=0,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "REFUSED"
    assert report.iterations == 0
    assert client.orders_created == 0


def test_real_pilot_watch_exits_armed_no_signal_after_max_iterations(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.watch(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        max_iterations=3,
        interval_seconds=0,
        signal_provider=lambda: _watch_signal(),
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "ARMED_NO_SIGNAL"
    assert report.iterations == 3
    assert report.order_attempted is False
    assert client.orders_created == 0
    assert len(report.updates) == 3


def test_real_pilot_watch_stops_after_first_order_attempt(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    signals = iter([_watch_signal(), _watch_signal("BUY_USDC"), _watch_signal("SELL_USDC")])

    report = engine.watch(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        max_iterations=5,
        interval_seconds=0,
        signal_provider=lambda: next(signals),
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "ORDER_PLACED"
    assert report.iterations == 2
    assert report.order_attempted is True
    assert client.orders_created == 1
    assert database.count_open_real_pilot_cycles(PROFILE) == 1


def test_real_pilot_watch_refuses_if_open_real_cycle_exists(test_config, tmp_path):
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

    report = engine.watch(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        max_iterations=5,
        interval_seconds=0,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "NOT_READY"
    assert report.iterations == 0
    assert client.orders_created == 0


def test_real_pilot_watch_requires_dry_run_ready_before_order_attempt(test_config, tmp_path):
    client = FakeRealPilotClient(usdt=Decimal("3"), usdc=Decimal("3"))
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.watch(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        max_iterations=5,
        interval_seconds=0,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "NOT_READY"
    assert report.iterations == 0
    assert client.orders_created == 0


def test_real_pilot_close_watch_refuses_without_confirmation(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    database.save_real_pilot_cycle(
        run_id="open",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )

    report = engine.close_watch(
        profile=PROFILE,
        confirmed=False,
        max_iterations=3,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "REFUSED"
    assert report.order_attempted is False
    assert client.orders_created == 0


def test_real_pilot_close_watch_refuses_if_no_open_cycle(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.close_watch(
        profile=PROFILE,
        confirmed=True,
        max_iterations=3,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "NO_OPEN_REAL_CYCLE"
    assert report.order_attempted is False
    assert client.orders_created == 0


def test_real_pilot_close_watch_closes_target_hit(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00069,
        ask=1.00070,
        order_avg_price=Decimal("1.00069"),
    )
    engine, database = _engine(tmp_path, test_config, client)
    cycle_id = database.save_real_pilot_cycle(
        run_id="open",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )

    report = engine.close_watch(
        profile=PROFILE,
        confirmed=True,
        max_iterations=3,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "CLOSE_ORDER_PLACED"
    assert report.order_attempted is True
    assert report.close_reason == "real_pilot_target"
    assert report.real_cycle_id == cycle_id
    assert client.orders_created == 1
    with database.connect() as conn:
        row = conn.execute(
            "SELECT status, close_price, net_profit, close_reason FROM real_pilot_cycles WHERE id = ?",
            (cycle_id,),
        ).fetchone()
        paper_count = conn.execute("SELECT COUNT(*) FROM paper_cycles").fetchone()[0]
    assert row[0] == "CLOSED"
    assert row[1] == 1.00069
    assert row[2] > 0
    assert row[3] == "real_pilot_target"
    assert paper_count == 0


def test_real_pilot_close_watch_does_not_open_new_entry(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)

    report = engine.close_watch(
        profile=PROFILE,
        confirmed=True,
        max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "NO_OPEN_REAL_CYCLE"
    assert client.orders_created == 0
    assert database.count_open_real_pilot_cycles(PROFILE) == 0


def test_real_pilot_status_shows_open_cycle_details(test_config, tmp_path):
    client = FakeRealPilotClient(bid=1.00067, ask=1.00068)
    engine, database = _engine(tmp_path, test_config, client)
    cycle_id = database.save_real_pilot_cycle(
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

    assert report.open_cycle_details is not None
    assert report.open_cycle_details.db_id == cycle_id
    assert report.open_cycle_details.direction == "SELL_USDC"
    assert report.open_cycle_details.quantity == Decimal("6.0")
    assert report.open_cycle_details.target_price < Decimal("1.00068")
    assert report.open_cycle_details.current_price == Decimal("1.00068")


def test_real_pilot_campaign_completes_normally(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00070,
        ask=1.00071,
        order_avg_price=Decimal("1.00069"),
    )
    engine, database = _engine(tmp_path, test_config, client)

    report = engine.run_campaign(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        target_cycles=2,
        confirmed=True,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        signal_max_iterations=1,
        close_max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "COMPLETED"
    assert report.completed_cycles == 2
    assert report.orders_sent == 4
    assert report.orders_filled == 4
    assert report.target_closes == 2
    assert report.net_profit >= 0
    assert client.orders_created == 4
    assert database.count_open_real_pilot_cycles(PROFILE) == 0


def test_real_pilot_campaign_stops_on_emergency_stop(test_config, tmp_path):
    client = FakeRealPilotClient()
    stop_path = tmp_path / "EMERGENCY_STOP"
    stop_path.write_text("stop", encoding="utf-8")
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = HFRealPilotEngine(database, _config(test_config), client, emergency_stop_path=stop_path)

    report = engine.run_campaign(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        target_cycles=2,
        confirmed=True,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        signal_max_iterations=1,
        close_max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "STOPPED"
    assert report.stop_reason == "safety_audit_failed"
    assert report.completed_cycles == 0
    assert client.orders_created == 0


def test_real_pilot_campaign_stops_on_daily_loss(test_config, tmp_path):
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

    report = engine.run_campaign(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        target_cycles=2,
        confirmed=True,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        signal_max_iterations=1,
        close_max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "STOPPED"
    assert report.stop_reason == "safety_audit_failed"
    assert report.completed_cycles == 0
    assert client.orders_created == 0


def test_real_pilot_campaign_stops_on_partial_order(test_config, tmp_path):
    client = FakeRealPilotClient(order_status="PARTIALLY_FILLED")
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.run_campaign(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        target_cycles=2,
        confirmed=True,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        signal_max_iterations=1,
        close_max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "STOPPED"
    assert report.stop_reason == "order_failed_or_unknown"
    assert report.completed_cycles == 0
    assert report.orders_sent == 1
    assert report.orders_filled == 0
    assert client.orders_created == 1


def test_real_pilot_campaign_status_shows_current_campaign(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00070,
        ask=1.00071,
        order_avg_price=Decimal("1.00069"),
    )
    engine, _database = _engine(tmp_path, test_config, client)

    campaign = engine.run_campaign(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        target_cycles=1,
        confirmed=True,
        signal_provider=lambda: _watch_signal("BUY_USDC"),
        signal_max_iterations=1,
        close_max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )
    status = engine.build_status(PROFILE)

    assert status.campaign_details is not None
    assert status.campaign_details.campaign_id == campaign.campaign_id
    assert status.campaign_details.completed_cycles == 1
    assert status.campaign_details.remaining_cycles == 0
