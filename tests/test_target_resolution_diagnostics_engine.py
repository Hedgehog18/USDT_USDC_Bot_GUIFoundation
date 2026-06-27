from pathlib import Path

from analytics.target_resolution_diagnostics_engine import TargetResolutionDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _snapshot(**overrides) -> dict:
    price = overrides.pop("price", 1.0)
    short_center = overrides.pop("short_center", 1.0001)
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


def test_target_resolution_detects_equivalent_tick_targets(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = TargetResolutionDiagnosticsEngine(database, test_config)

    comparison = engine.compare(0.0005, 0.00075)

    assert comparison.identical_after_ceil_normalization is True
    assert comparison.identical_after_rounding is True
    assert comparison.warning == "Equivalent effective target."


def test_target_resolution_reports_tick_normalization(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = TargetResolutionDiagnosticsEngine(database, test_config)

    item = engine.resolve_target(0.0005, reference_price=1.0)

    assert item.raw_target_distance == 0.000005
    assert item.raw_ticks == 0.5
    assert item.ceil_ticks == 1
    assert item.ceil_effective_target_percent == 0.001
    assert item.has_sub_tick_distance is True


def test_target_resolution_reports_epsilon_equivalence(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = TargetResolutionDiagnosticsEngine(database, test_config)

    comparison = engine.compare(0.0005, 0.000501)

    assert comparison.identical_after_epsilon is True


def test_target_resolution_simulation_compare_identical(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:00:05", price=1.00002, short_center=1.0001),
    ])
    engine = TargetResolutionDiagnosticsEngine(database, test_config)

    report = engine.compare_simulation(
        0.0005,
        0.00075,
        scenario="short_term_mean_reversion",
        max_holding_seconds=270,
    )

    assert report.compared_cycles == 1
    assert report.identical_outcomes == 1
    assert report.different_outcomes == 0
    assert report.similarity == 1.0
    assert "effectively equivalent" in report.message


def test_target_resolution_simulation_compare_different(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:00:05", price=1.000006, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:00:10", price=1.00002, short_center=1.0001),
    ])
    engine = TargetResolutionDiagnosticsEngine(database, test_config)

    report = engine.compare_simulation(
        0.0005,
        0.0015,
        scenario="short_term_mean_reversion",
        max_holding_seconds=270,
    )

    assert report.compared_cycles == 1
    assert report.different_outcomes == 1
