from dataclasses import replace

import pytest

from analytics.hf_post_exit_observer_statistics_engine import HFPostExitObserverStatisticsEngine
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _database(tmp_path) -> DatabaseManager:
    return DatabaseManager(str(tmp_path / "bot.sqlite"))


def _closed_cycle(
    database: DatabaseManager,
    *,
    direction: str = "BUY_USDC",
    open_price: float = 1.00070000,
    close_reason: str = "max_holding_270s",
    net_profit: float = 0.0,
) -> int:
    cycle_id = database.save_real_pilot_cycle(
        run_id=f"run-{direction}-{close_reason}",
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
        gross_profit=net_profit,
        net_profit=net_profit,
        close_reason=close_reason,
    )
    return cycle_id


def _summary(database: DatabaseManager, cycle_id: int, *, touched: bool, seconds: float | None, mfe: float, mae: float, closest: float) -> None:
    database.save_real_pilot_post_exit_summary(
        real_cycle_id=cycle_id,
        campaign_id=None,
        started_at="2026-07-20T12:00:00",
        finished_at="2026-07-20T12:05:00",
        duration_seconds=300,
        interval_seconds=5,
        snapshots_count=3,
        post_exit_mfe=mfe,
        post_exit_mae=mae,
        max_price=None,
        min_price=None,
        post_exit_target_touched=touched,
        time_to_post_target=seconds,
        closest_distance_after_exit=closest,
        status="COMPLETED",
    )


def test_post_exit_statistics_empty_dataset(test_config, tmp_path):
    report = HFPostExitObserverStatisticsEngine(_database(tmp_path), test_config).build_report(PROFILE)

    assert report.completed_observer_records == 0
    assert report.timeout_cycles == 0
    assert report.late_target_touch_rate == 0
    assert report.recommendation == "NEED_MORE_DATA"


def test_post_exit_statistics_one_timeout_with_late_target(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = _closed_cycle(database)
    _summary(database, cycle_id, touched=True, seconds=42, mfe=0.00001, mae=-0.00002, closest=0)

    report = HFPostExitObserverStatisticsEngine(database, test_config).build_report(PROFILE)

    assert report.timeout_cycles == 1
    assert report.timeout_reached_after_exit == 1
    assert report.timeout_never_reached == 0
    assert report.late_target_touch_rate == 1
    assert report.time_to_target_stats.average == 42
    assert report.time_buckets[60] == 1


def test_post_exit_statistics_one_timeout_without_late_target(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = _closed_cycle(database)
    _summary(database, cycle_id, touched=False, seconds=None, mfe=0.000001, mae=-0.00002, closest=0.000004)

    report = HFPostExitObserverStatisticsEngine(database, test_config).build_report(PROFILE)

    assert report.timeout_cycles == 1
    assert report.timeout_reached_after_exit == 0
    assert report.timeout_never_reached == 1
    assert report.time_to_target_stats.average is None


def test_post_exit_statistics_counts_target_cycles_separately(test_config, tmp_path):
    database = _database(tmp_path)
    timeout_id = _closed_cycle(database, close_reason="max_holding_270s")
    target_id = _closed_cycle(database, close_reason="real_pilot_target", net_profit=0.00005)
    _summary(database, timeout_id, touched=True, seconds=30, mfe=0.00001, mae=-0.00001, closest=0)
    _summary(database, target_id, touched=True, seconds=0, mfe=0.00001, mae=-0.00001, closest=0)

    report = HFPostExitObserverStatisticsEngine(database, test_config).build_report(PROFILE)

    assert report.timeout_cycles == 1
    assert report.target_cycles == 1
    assert report.timeout_reached_after_exit == 1
    assert report.late_target_touch_rate == 1


def test_post_exit_statistics_buy_sell_breakdown(test_config, tmp_path):
    database = _database(tmp_path)
    buy_id = _closed_cycle(database, direction="BUY_USDC")
    sell_id = _closed_cycle(database, direction="SELL_USDC")
    _summary(database, buy_id, touched=True, seconds=25, mfe=0.00001, mae=-0.00001, closest=0)
    _summary(database, sell_id, touched=False, seconds=None, mfe=0.000002, mae=-0.00003, closest=0.000005)

    report = HFPostExitObserverStatisticsEngine(database, test_config).build_report(PROFILE)
    by_direction = {row.direction: row for row in report.direction_stats}

    assert by_direction["BUY_USDC"].timeout_cycles == 1
    assert by_direction["BUY_USDC"].late_target_touch_count == 1
    assert by_direction["SELL_USDC"].timeout_cycles == 1
    assert by_direction["SELL_USDC"].never_reached_count == 1


def test_post_exit_statistics_category_aggregation(test_config, tmp_path):
    database = _database(tmp_path)
    cycle_id = _closed_cycle(database)
    _summary(database, cycle_id, touched=True, seconds=20, mfe=0.00001, mae=-0.00001, closest=0)

    report = HFPostExitObserverStatisticsEngine(database, replace(test_config, max_allowed_spread=0.0002)).build_report(PROFILE)
    categories = {row.category: row for row in report.category_stats}

    assert "insufficient_data" in categories
    assert categories["insufficient_data"].cycles_count == 1
    assert categories["insufficient_data"].post_exit_target_touch_count == 1
    assert categories["insufficient_data"].average_mfe == pytest.approx(0.00001)
