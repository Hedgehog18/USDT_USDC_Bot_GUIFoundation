from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from analytics.hf_post_exit_observer import HFPostExitObserver, POST_EXIT_OBSERVER_DISABLED
from market.binance_market_data_provider import BidAsk
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


class FakeMarketProvider:
    def __init__(self, prices: list[float]) -> None:
        self.prices = prices
        self.index = 0

    def get_bid_ask(self, symbol: str) -> BidAsk:
        price = self.prices[min(self.index, len(self.prices) - 1)]
        self.index += 1
        return BidAsk(bid=price, ask=price)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start
        self.monotonic_seconds = 0.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.monotonic_seconds

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.monotonic_seconds += seconds


def _database(tmp_path) -> DatabaseManager:
    return DatabaseManager(str(tmp_path / "bot.sqlite"))


def _closed_cycle(database: DatabaseManager, *, direction: str = "BUY_USDC", open_price: float = 1.0) -> int:
    cycle_id = database.save_real_pilot_cycle(
        run_id="real-run",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction=direction,
        status="OPEN",
        open_price=open_price,
        quantity=5,
        stake_usdt=5,
    )
    database.close_real_pilot_cycle(
        cycle_id,
        close_price=open_price,
        gross_profit=0,
        net_profit=0,
        close_reason="max_holding_270s",
    )
    return cycle_id


def test_post_exit_observer_tables_are_created(tmp_path):
    database = _database(tmp_path)

    with database.connect() as conn:
        snapshot_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='real_pilot_post_exit_observer_snapshots'"
        ).fetchone()
        summary_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='real_pilot_post_exit_observer_summaries'"
        ).fetchone()

    assert snapshot_table is not None
    assert summary_table is not None


def test_post_exit_observer_stores_snapshots_and_summary(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = _closed_cycle(database, direction="BUY_USDC", open_price=1.0)
    start = datetime(2026, 7, 20, 12, 0, 0)
    with database.connect() as conn:
        conn.execute("UPDATE real_pilot_cycles SET closed_at = ? WHERE id = ?", (start.isoformat(), cycle_id))
        conn.commit()
    clock = FakeClock(start)
    observer = HFPostExitObserver(
        database,
        replace(test_config, post_exit_observer_enabled=True),
        market_provider=FakeMarketProvider([1.000001, 1.000006, 0.999999]),
    )

    result = observer.observe(
        profile=PROFILE,
        real_cycle_id=cycle_id,
        duration_seconds=10,
        interval_seconds=5,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )

    snapshots = database.load_real_pilot_post_exit_snapshots(cycle_id)
    summary = database.load_real_pilot_post_exit_summary(cycle_id)
    assert result.snapshots_count == 3
    assert len(snapshots) == 3
    assert summary is not None
    assert summary["snapshots_count"] == 3
    assert result.post_exit_target_touched is True
    assert result.time_to_post_target == 5
    assert result.post_exit_mfe == pytest.approx(0.000006)
    assert result.post_exit_mae == pytest.approx(-0.000001)


def test_post_exit_observer_calculates_sell_excursion(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = _closed_cycle(database, direction="SELL_USDC", open_price=1.0)
    start = datetime(2026, 7, 20, 12, 0, 0)
    with database.connect() as conn:
        conn.execute("UPDATE real_pilot_cycles SET closed_at = ? WHERE id = ?", (start.isoformat(), cycle_id))
        conn.commit()
    clock = FakeClock(start)
    observer = HFPostExitObserver(
        database,
        replace(test_config, post_exit_observer_enabled=True),
        market_provider=FakeMarketProvider([0.999999, 0.999994, 1.000001]),
    )

    result = observer.observe(
        profile=PROFILE,
        real_cycle_id=cycle_id,
        duration_seconds=10,
        interval_seconds=5,
        sleep_fn=clock.sleep,
        now_fn=clock.now,
        monotonic_fn=clock.monotonic,
    )

    assert result.post_exit_target_touched is True
    assert result.time_to_post_target == 5
    assert result.post_exit_mfe == pytest.approx(0.000006)
    assert result.post_exit_mae == pytest.approx(-0.000001)


def test_post_exit_observer_disabled_writes_summary_without_snapshots(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = _closed_cycle(database)
    observer = HFPostExitObserver(
        database,
        replace(test_config, post_exit_observer_enabled=False),
        market_provider=FakeMarketProvider([1.0]),
    )

    result = observer.observe(profile=PROFILE, real_cycle_id=cycle_id)

    assert result.status == POST_EXIT_OBSERVER_DISABLED
    assert result.snapshots_count == 0
    assert database.load_real_pilot_post_exit_snapshots(cycle_id) == []
    summary = database.load_real_pilot_post_exit_summary(cycle_id)
    assert summary is not None
    assert summary["status"] == POST_EXIT_OBSERVER_DISABLED


def test_post_exit_observer_rejects_open_cycle(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = database.save_real_pilot_cycle(
        run_id="open-run",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        quantity=5,
        stake_usdt=5,
    )
    observer = HFPostExitObserver(database, test_config, market_provider=FakeMarketProvider([1.0]))

    result = observer.observe(profile=PROFILE, real_cycle_id=cycle_id)

    assert result.status == "CYCLE_NOT_CLOSED"
    assert result.snapshots_count == 0


def test_post_exit_target_touch_boundaries_buy(test_config, tmp_path):
    database = _database(tmp_path)
    observer = HFPostExitObserver(database, test_config, market_provider=FakeMarketProvider([1.0]))
    cycle = {"id": 1, "direction": "BUY_USDC", "open_price": "1.00070000", "close_price": "1.00070000", "close_reason": "max_holding_270s"}

    below = observer.calculate_result(cycle, [{"price": "1.00070499", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}])
    equal = observer.calculate_result(cycle, [{"price": "1.00070500", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}])
    above = observer.calculate_result(cycle, [{"price": "1.00070501", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}])

    assert below.post_exit_target_touched is False
    assert below.closest_distance_after_exit == pytest.approx(0.00000001)
    assert equal.post_exit_target_touched is True
    assert equal.closest_distance_after_exit == 0
    assert above.post_exit_target_touched is True


def test_post_exit_target_touch_boundaries_sell(test_config, tmp_path):
    database = _database(tmp_path)
    observer = HFPostExitObserver(database, test_config, market_provider=FakeMarketProvider([1.0]))
    cycle = {"id": 1, "direction": "SELL_USDC", "open_price": "1.00070000", "close_price": "1.00070000", "close_reason": "max_holding_270s"}

    above = observer.calculate_result(cycle, [{"price": "1.00069501", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}])
    equal = observer.calculate_result(cycle, [{"price": "1.00069500", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}])
    below = observer.calculate_result(cycle, [{"price": "1.00069499", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}])

    assert above.post_exit_target_touched is False
    assert above.closest_distance_after_exit == pytest.approx(0.00000001)
    assert equal.post_exit_target_touched is True
    assert equal.closest_distance_after_exit == 0
    assert below.post_exit_target_touched is True


def test_post_exit_target_touch_uses_decimal_without_float_drift(test_config, tmp_path):
    database = _database(tmp_path)
    observer = HFPostExitObserver(database, test_config, market_provider=FakeMarketProvider([1.0]))
    cycle = {"id": 17, "direction": "BUY_USDC", "open_price": "1.0007000", "close_price": "1.00070000", "close_reason": "max_holding_270s"}

    result = observer.calculate_result(
        cycle,
        [{"price": "1.0007050000", "timestamp": "2026-07-20T12:00:05", "seconds_after_exit": 5}],
    )

    assert result.max_price == pytest.approx(1.000705)
    assert result.closest_distance_after_exit == 0
    assert result.post_exit_target_touched is True
    assert result.time_to_post_target == 5


def test_post_exit_target_closed_cycle_uses_revisit_fields(test_config, tmp_path):
    database = _database(tmp_path)
    observer = HFPostExitObserver(database, test_config, market_provider=FakeMarketProvider([1.0]))
    cycle = {"id": 2, "direction": "BUY_USDC", "open_price": "1.00070000", "close_price": "1.00070500", "close_reason": "real_pilot_target"}

    result = observer.calculate_result(
        cycle,
        [{"price": "1.00070500", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0}],
    )

    assert result.target_was_reached_before_exit is True
    assert result.target_satisfied_at_observer_start is True
    assert result.post_exit_target_touched is None
    assert result.target_revisited_after_exit is True
    assert result.time_to_target_revisit == 0


def test_post_exit_observer_expected_count_and_average_interval(test_config, tmp_path):
    database = _database(tmp_path)
    observer = HFPostExitObserver(database, test_config, market_provider=FakeMarketProvider([1.0]))
    cycle = {"id": 3, "direction": "BUY_USDC", "open_price": "1.00070000", "close_price": "1.00070000", "close_reason": "max_holding_270s"}

    result = observer.calculate_result(
        cycle,
        [
            {"price": "1.00070000", "timestamp": "2026-07-20T12:00:00", "seconds_after_exit": 0},
            {"price": "1.00070000", "timestamp": "2026-07-20T12:00:05", "seconds_after_exit": 5},
            {"price": "1.00070000", "timestamp": "2026-07-20T12:00:10", "seconds_after_exit": 10},
        ],
        duration_seconds=300,
        interval_seconds=5,
    )

    assert result.expected_snapshots_count == 61
    assert result.effective_average_interval_seconds == 5
