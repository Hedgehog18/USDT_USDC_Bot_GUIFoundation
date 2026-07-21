import json
from dataclasses import replace
from decimal import Decimal

from analytics.hf_real_dry_run_engine import AccountBalances, ExchangeSymbolRules
from analytics.hf_real_pilot_engine import (
    HFRealPilotEngine,
    HFRealPilotSignalSnapshot,
    RealOrderResult,
    evaluate_real_target_condition,
)
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
        order_avg_prices: list[Decimal] | None = None,
    ) -> None:
        self.usdt = usdt
        self.usdc = usdc
        self.order_status = order_status
        self.orders_created = 0
        self.bid = bid
        self.ask = ask
        self.order_avg_price = order_avg_price
        self.order_avg_prices = list(order_avg_prices or [])
        self.order_sides: list[str] = []
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
        self.order_sides.append(side)
        avg_price = self.order_avg_prices.pop(0) if self.order_avg_prices else self.order_avg_price
        return RealOrderResult(
            order_id="mock-order-1",
            status=self.order_status,
            executed_qty=quantity if self.order_status == "FILLED" else Decimal("0"),
            avg_price=avg_price if self.order_status == "FILLED" else Decimal("0"),
            raw_response={"orderId": "mock-order-1", "status": self.order_status, "side": side},
        )


class FakePostExitObserverLauncher:
    def __init__(self, *, started: bool = True) -> None:
        self.started = started
        self.calls: list[tuple[str, int]] = []

    def start(self, *, profile: str, real_cycle_id: int) -> bool:
        self.calls.append((profile, real_cycle_id))
        return self.started


def _config(test_config):
    return replace(test_config, symbol="USDCUSDT", mode="DEMO", max_allowed_spread=0.0002)


def _engine(tmp_path, test_config, client=None, post_exit_launcher=None):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    return HFRealPilotEngine(
        database,
        _config(test_config),
        client or FakeRealPilotClient(),
        emergency_stop_path=tmp_path / "EMERGENCY_STOP",
        post_exit_observer_launcher=post_exit_launcher or FakePostExitObserverLauncher(),
    ), database


def _closed_real_loss(database: DatabaseManager, *, run_id: str, net_profit: float = -0.1) -> int:
    cycle_id = database.save_real_pilot_cycle(
        run_id=run_id,
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )
    database.close_real_pilot_cycle(
        cycle_id,
        close_price=1.00067,
        gross_profit=net_profit,
        net_profit=net_profit,
        close_reason="max_holding_270s",
    )
    return cycle_id


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


def test_real_pilot_safety_reset_refuses_without_confirmation(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.reset_safety(
        profile=PROFILE,
        reason="run new campaign with blackbox recorder",
        confirmed=False,
    )

    assert report.status == "REFUSED"
    assert report.reset_id is None
    assert "explicit_confirmation" in {check.name for check in report.failed_checks}
    assert client.orders_created == 0


def test_real_pilot_safety_reset_refuses_without_reason(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, _database = _engine(tmp_path, test_config, client)

    report = engine.reset_safety(profile=PROFILE, reason="   ", confirmed=True)

    assert report.status == "REFUSED"
    assert report.reset_id is None
    assert "reason_present" in {check.name for check in report.failed_checks}
    assert client.orders_created == 0


def test_real_pilot_safety_reset_does_not_delete_cycles_or_orders(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    _closed_real_loss(database, run_id="loss-run")
    database.save_real_pilot_order_event(
        run_id="loss-run",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        side="BUY",
        quantity=6,
        status="FILLED",
        request_payload="{}",
        response_payload="{}",
    )

    report = engine.reset_safety(
        profile=PROFILE,
        reason="run new campaign with blackbox recorder",
        confirmed=True,
    )
    status = engine.build_status(PROFILE)

    assert report.status == "SAFETY_RESET_RECORDED"
    assert report.reset_id is not None
    assert status.closed_cycles == 1
    assert status.order_events == 1
    assert status.net_profit == -0.1
    assert status.latest_safety_reset_reason == "run new campaign with blackbox recorder"
    assert client.orders_created == 0


def test_real_pilot_consecutive_losses_counted_after_reset(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    for index in range(3):
        _closed_real_loss(database, run_id=f"loss-before-reset-{index}")

    blocked = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True)
    reset = engine.reset_safety(
        profile=PROFILE,
        reason="run new campaign with blackbox recorder",
        confirmed=True,
    )
    after_reset = engine.build_status(PROFILE)
    allowed = engine.run_once(profile=PROFILE, pilot_stake=Decimal("6"), confirmed=True, entry_signal=None)

    assert "max_consecutive_losses" in {check.name for check in blocked.failed_checks}
    assert reset.status == "SAFETY_RESET_RECORDED"
    assert after_reset.consecutive_losses_since_reset == 0
    assert allowed.status == "ARMED_WAITING_FOR_SIGNAL"
    assert "max_consecutive_losses" not in {check.name for check in allowed.failed_checks}


def test_real_pilot_campaign_can_pass_consecutive_loss_gate_after_reset(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    for index in range(3):
        _closed_real_loss(database, run_id=f"loss-before-reset-{index}")
    engine.reset_safety(
        profile=PROFILE,
        reason="run new campaign with blackbox recorder",
        confirmed=True,
    )

    report = engine.run_campaign(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        target_cycles=1,
        confirmed=True,
        signal_provider=lambda: _watch_signal(),
        signal_max_iterations=1,
        close_max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.stop_reason == "no_signal_before_limit"
    assert not any(check.name == "max_consecutive_losses" and not check.ok for check in report.checks)
    assert client.orders_created == 0


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


def test_real_target_condition_uses_decimal_boundary_for_buy_and_sell():
    buy_below = evaluate_real_target_condition(
        direction="BUY_USDC",
        target_price=Decimal("1.00068500"),
        bid=Decimal("1.00068499"),
        ask=Decimal("1.00069500"),
    )
    buy_equal = evaluate_real_target_condition(
        direction="BUY_USDC",
        target_price=Decimal("1.00068500"),
        bid=Decimal("1.00068500"),
        ask=Decimal("1.00069500"),
    )
    sell_above = evaluate_real_target_condition(
        direction="SELL_USDC",
        target_price=Decimal("1.00067500"),
        bid=Decimal("1.00066500"),
        ask=Decimal("1.00067501"),
    )
    sell_equal = evaluate_real_target_condition(
        direction="SELL_USDC",
        target_price=Decimal("1.00067500"),
        bid=Decimal("1.00066500"),
        ask=Decimal("1.00067500"),
    )

    assert buy_below.executable_price == Decimal("1.00068499")
    assert buy_below.target_condition_result is False
    assert buy_equal.target_condition_result is True
    assert sell_above.executable_price == Decimal("1.00067501")
    assert sell_above.target_condition_result is False
    assert sell_equal.target_condition_result is True


def test_real_pilot_immediate_post_fill_buy_target_closes_standard_flow(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00069,
        ask=1.00070,
        order_avg_prices=[Decimal("1.00068000"), Decimal("1.00069000")],
    )
    engine, database = _engine(tmp_path, test_config, client)

    report = engine.run_once(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        entry_signal="BUY_USDC",
    )

    assert report.status == "CLOSE_ORDER_PLACED"
    assert report.real_cycle_id is not None
    assert client.orders_created == 2
    assert client.order_sides == ["BUY", "SELL"]
    assert database.count_open_real_pilot_cycles(PROFILE) == 0
    cycle = database.load_real_pilot_cycle_by_id(report.real_cycle_id, PROFILE)
    assert cycle["status"] == "CLOSED"
    assert cycle["close_reason"] == "real_pilot_target"
    with database.connect() as conn:
        close_attempts = conn.execute(
            "SELECT COUNT(*) FROM real_pilot_order_events WHERE status = 'ATTEMPTED_CLOSE'",
        ).fetchone()[0]
        raw = conn.execute(
            """
            SELECT raw_payload_json
            FROM real_pilot_market_snapshots
            WHERE real_cycle_id = ?
              AND source = 'real_pilot_close_watch'
            ORDER BY id ASC
            LIMIT 1
            """,
            (report.real_cycle_id,),
        ).fetchone()[0]
    payload = json.loads(raw)
    assert close_attempts == 1
    assert payload["close_trigger_source"] == "immediate_post_fill"
    assert payload["immediate_target_condition_result"] is True
    assert Decimal(payload["immediate_target_check_bid"]) == Decimal("1.00069000")


def test_real_pilot_immediate_post_fill_sell_target_closes_standard_flow(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00066,
        ask=1.00067,
        order_avg_prices=[Decimal("1.00068000"), Decimal("1.00067000")],
    )
    engine, database = _engine(tmp_path, test_config, client)

    report = engine.run_once(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        entry_signal="SELL_USDC",
    )

    assert report.status == "CLOSE_ORDER_PLACED"
    assert report.real_cycle_id is not None
    assert client.orders_created == 2
    assert client.order_sides == ["SELL", "BUY"]
    cycle = database.load_real_pilot_cycle_by_id(report.real_cycle_id, PROFILE)
    assert cycle["status"] == "CLOSED"
    assert cycle["close_reason"] == "real_pilot_target"


def test_real_pilot_immediate_false_leaves_cycle_for_regular_watcher(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00067,
        ask=1.00068,
        order_avg_price=Decimal("1.00068000"),
    )
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
        raw = conn.execute(
            """
            SELECT raw_payload_json
            FROM real_pilot_market_snapshots
            WHERE real_cycle_id = ?
              AND source = 'real_pilot_close_watch'
            ORDER BY id ASC
            LIMIT 1
            """,
            (report.real_cycle_id,),
        ).fetchone()[0]
    payload = json.loads(raw)
    assert payload["close_trigger_source"] == "immediate_post_fill"
    assert payload["immediate_target_condition_result"] is False


def test_real_pilot_regular_watcher_does_not_duplicate_immediate_close(test_config, tmp_path):
    client = FakeRealPilotClient(
        bid=1.00069,
        ask=1.00070,
        order_avg_prices=[Decimal("1.00068000"), Decimal("1.00069000")],
    )
    engine, database = _engine(tmp_path, test_config, client)
    entry = engine.run_once(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        entry_signal="BUY_USDC",
    )

    close = engine.close_watch(
        profile=PROFILE,
        confirmed=True,
        max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert entry.status == "CLOSE_ORDER_PLACED"
    assert close.status == "NO_OPEN_REAL_CYCLE"
    assert client.orders_created == 2
    with database.connect() as conn:
        close_attempts = conn.execute(
            "SELECT COUNT(*) FROM real_pilot_order_events WHERE status = 'ATTEMPTED_CLOSE'",
        ).fetchone()[0]
    assert close_attempts == 1


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
    post_exit_launcher = FakePostExitObserverLauncher()
    engine, database = _engine(tmp_path, test_config, client, post_exit_launcher)
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
    assert post_exit_launcher.calls == [(PROFILE, cycle_id)]
    assert "Post exit observer started." in report.message


def test_real_pilot_close_watch_records_target_check_instrumentation(test_config, tmp_path):
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
        max_iterations=1,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert report.status == "CLOSE_ORDER_PLACED"
    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT raw_payload_json
            FROM real_pilot_market_snapshots
            WHERE real_cycle_id = ?
              AND source = 'real_pilot_close_watch'
            ORDER BY id ASC
            LIMIT 1
            """,
            (cycle_id,),
        ).fetchone()
    assert row is not None
    payload = json.loads(row[0])
    assert payload["close_watcher_started_at"]
    assert payload["target_check_at"]
    assert payload["iteration"] == 1
    assert payload["target_check_bid"] == "1.00069"
    assert Decimal(payload["target_check_ask"]) == Decimal("1.00070")
    assert payload["target_condition_result"] is True
    assert payload["seconds_since_entry_fill"] is not None


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
    assert report.open_cycle_details.blackbox_snapshots_count == 0


def test_real_pilot_status_shows_blackbox_count_for_open_cycle(test_config, tmp_path):
    client = FakeRealPilotClient(bid=1.00067, ask=1.00068)
    engine, database = _engine(tmp_path, test_config, client)
    cycle_id = database.save_real_pilot_cycle(
        run_id="status",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.00068,
        quantity=6,
        stake_usdt=6,
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=cycle_id,
        campaign_id="campaign-1",
        phase="tracking",
        symbol="USDCUSDT",
        price=1.00069,
        bid=1.000685,
        ask=1.000695,
        mid=1.00069,
        spread=0.00001,
        short_center=1.00068,
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.000685,
        distance_to_target=-0.000005,
        unrealized_pnl=0.00006,
        open_real_cycles=1,
        source="TEST",
    )

    report = engine.build_status(PROFILE)

    assert report.open_cycle_details is not None
    assert report.open_cycle_details.blackbox_snapshots_count == 1


def test_real_pilot_status_shows_latest_closed_blackbox_target_touch(test_config, tmp_path):
    client = FakeRealPilotClient()
    engine, database = _engine(tmp_path, test_config, client)
    cycle_id = database.save_real_pilot_cycle(
        run_id="status",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        quantity=10,
        stake_usdt=10,
    )
    database.close_real_pilot_cycle(
        cycle_id,
        close_price=1.000006,
        gross_profit=0.00006,
        net_profit=0.00006,
        close_reason="real_pilot_target",
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=cycle_id,
        campaign_id="campaign-1",
        phase="tracking",
        symbol="USDCUSDT",
        price=1.000006,
        bid=1.000001,
        ask=1.000011,
        mid=1.000006,
        spread=0.00001,
        short_center=1.0,
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.000005,
        distance_to_target=-0.000001,
        unrealized_pnl=0.00006,
        open_real_cycles=0,
        source="TEST",
    )

    report = engine.build_status(PROFILE)

    assert report.latest_closed_blackbox is not None
    assert report.latest_closed_blackbox.db_id == cycle_id
    assert report.latest_closed_blackbox.snapshots_count == 1
    assert report.latest_closed_blackbox.target_touched is True


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
    assert report.failed_checks
    assert any(check.name == "emergency_stop_clear" and not check.ok for check in report.checks)


def test_real_pilot_campaign_diagnostics_match_small_pilot_failure(test_config, tmp_path):
    client = FakeRealPilotClient()
    stop_path = tmp_path / "EMERGENCY_STOP"
    stop_path.write_text("stop", encoding="utf-8")
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = HFRealPilotEngine(database, _config(test_config), client, emergency_stop_path=stop_path)

    campaign = engine.run_campaign(
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
    single = engine.run_once(
        profile=PROFILE,
        pilot_stake=Decimal("6"),
        confirmed=True,
        entry_signal=None,
    )

    campaign_diagnostics = [(check.name, check.ok, check.message) for check in campaign.checks]
    single_diagnostics = [(check.name, check.ok, check.message) for check in single.checks]
    assert campaign_diagnostics == single_diagnostics


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
