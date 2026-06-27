from pathlib import Path

from analytics.micro_cycle_sim_engine import MicroCycleSimulationEngine
from storage.database_manager import DatabaseManager


def _snapshot(**overrides) -> dict:
    price = overrides.pop("price", 1.0)
    short_center = overrides.pop("short_center", 1.0)
    base = {
        "timestamp": "2026-06-26T13:00:00",
        "symbol": "USDCUSDT",
        "price": price,
        "bid": price - 0.00001,
        "ask": price + 0.00001,
        "mid_price": price,
        "spread": 0.00001,
        "work_position": 20.0,
        "micro_trend": "BUY_DOMINANT",
        "entry_zone": "BUY",
        "buy_zone": True,
        "sell_zone": False,
        "volatility_regime": "LOW",
        "market_regime": "NORMAL",
        "distance_to_long_center": 0.0,
        "distance_to_short_center": price - short_center,
        "distance_to_work_center": 0.0,
        "order_book_pressure": "BALANCED",
        "session": "LONDON_NEW_YORK_OVERLAP",
        "price_change_5_sec": 0.0,
        "price_change_10_sec": 0.0,
        "price_change_30_sec": 0.0,
        "price_change_1_min": 0.0,
        "price_change_5_min": 0.0,
        "would_open_cycle": True,
        "reason_if_not": "",
        "data_source": "TEST",
    }
    base.update(overrides)
    return base


def _database_with_snapshots(tmp_path: Path, snapshots: list[dict]) -> DatabaseManager:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    for snapshot in snapshots:
        database.save_hf_market_snapshot(snapshot)
    return database


def test_micro_cycle_sim_empty_dataset(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = MicroCycleSimulationEngine(database, test_config).build_report()

    assert report.best_result is not None
    assert report.best_result.total_samples == 0
    assert report.recommendation == "NEEDS_MORE_DATA"


def test_micro_cycle_sim_opens_and_closes_buy_on_target(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:00:05", price=1.00002, work_position=50.0, micro_trend="NEUTRAL"),
    ])

    report = MicroCycleSimulationEngine(database, test_config).build_report(
        scenario="current_mean_reversion",
        target_percent=0.001,
    )

    result = report.best_result
    assert result is not None
    assert result.cycles_opened == 1
    assert result.closed_by_target == 1
    assert result.net_profit > 0


def test_micro_cycle_sim_opens_and_closes_sell_on_target(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(
            timestamp="2026-06-26T13:00:00",
            price=1.0,
            work_position=80.0,
            micro_trend="SELL_DOMINANT",
            entry_zone="SELL",
            buy_zone=False,
            sell_zone=True,
        ),
        _snapshot(timestamp="2026-06-26T13:00:05", price=0.99998, work_position=50.0, micro_trend="NEUTRAL"),
    ])

    report = MicroCycleSimulationEngine(database, test_config).build_report(
        scenario="current_mean_reversion",
        target_percent=0.001,
    )

    result = report.best_result
    assert result is not None
    assert result.cycles_opened == 1
    assert result.closed_by_target == 1
    assert result.net_profit > 0


def test_micro_cycle_sim_does_not_open_second_cycle_while_active(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0, work_position=20.0),
        _snapshot(timestamp="2026-06-26T13:00:05", price=0.99999, work_position=20.0),
        _snapshot(timestamp="2026-06-26T13:00:10", price=0.99998, work_position=20.0),
    ])

    report = MicroCycleSimulationEngine(database, test_config).build_report(
        scenario="spread_only",
        target_percent=0.01,
    )

    result = report.best_result
    assert result is not None
    assert result.cycles_opened == 1
    assert result.still_open_at_end == 1
    assert result.skipped_opportunities_due_to_active_cycle == 2


def test_micro_cycle_sim_timeout_close_works(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:10:00", price=0.99999, work_position=50.0, micro_trend="NEUTRAL"),
    ])

    report = MicroCycleSimulationEngine(database, test_config).build_report(
        scenario="current_mean_reversion",
        target_percent=0.01,
        max_holding_seconds=300,
    )

    result = report.best_result
    assert result is not None
    assert result.cycles_opened == 1
    assert result.closed_by_timeout == 1
    assert result.still_open_at_end == 0
    assert result.average_holding_seconds == 600.0


def test_micro_cycle_sim_net_profit_uses_effective_fees(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:00:05", price=1.00002, work_position=50.0, micro_trend="NEUTRAL"),
    ])

    result = MicroCycleSimulationEngine(database, test_config).build_report(
        scenario="current_mean_reversion",
        target_percent=0.001,
    ).best_result

    assert result is not None
    assert round(result.gross_profit, 8) == round(result.net_profit, 8)
