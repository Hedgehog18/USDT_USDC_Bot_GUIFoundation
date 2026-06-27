from pathlib import Path

from analytics.micro_cycle_grid_search_engine import (
    MICRO_CYCLE_GRID_MAX_HOLDING_SECONDS,
    MICRO_CYCLE_GRID_TARGETS,
    MicroCycleGridSearchEngine,
)
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


def test_micro_cycle_grid_search_counts_combinations(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:05:00", price=1.0001, work_position=50.0),
    ])

    report = MicroCycleGridSearchEngine(database, test_config).run(
        scenario="short_term_mean_reversion",
        top=5,
    )

    assert report.total_results == len(MICRO_CYCLE_GRID_TARGETS) * len(MICRO_CYCLE_GRID_MAX_HOLDING_SECONDS)
    assert len(report.top_by_score) == 5


def test_micro_cycle_grid_search_ranking_sorts_by_score(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:01:00", price=1.0002, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:02:00", price=1.0, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:03:00", price=1.0002, short_center=1.0001),
    ])

    report = MicroCycleGridSearchEngine(database, test_config).run(
        scenario="short_term_mean_reversion",
        top=10,
    )

    scores = [item.recommendation_score for item in report.top_by_score]
    assert scores == sorted(scores, reverse=True)


def test_micro_cycle_grid_search_balanced_filter(test_config, tmp_path: Path) -> None:
    snapshots = []
    for index in range(10):
        entry_minute = index * 2
        close_minute = entry_minute + 1
        snapshots.append(
            _snapshot(
                timestamp=f"2026-06-26T13:{entry_minute:02d}:00",
                price=1.0,
                short_center=1.0001,
            )
        )
        snapshots.append(
            _snapshot(
                timestamp=f"2026-06-26T13:{close_minute:02d}:00",
                price=1.0002,
                short_center=1.0001,
            )
        )
    database = _database_with_snapshots(tmp_path, snapshots)

    report = MicroCycleGridSearchEngine(database, test_config).run(
        scenario="short_term_mean_reversion",
        min_cycles_day=1,
        max_drawdown=0.005,
        top=5,
    )

    assert report.balanced_candidates
    assert all(item.net_profit > 0 for item in report.balanced_candidates)


def test_micro_cycle_grid_search_export_csv(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0, short_center=1.0001),
        _snapshot(timestamp="2026-06-26T13:01:00", price=1.0002, short_center=1.0001),
    ])
    engine = MicroCycleGridSearchEngine(database, test_config)
    results = engine.all_results(scenario="short_term_mean_reversion")

    output_path = engine.export_csv(tmp_path / "grid.csv", results)

    text = output_path.read_text(encoding="utf-8")
    assert "scenario,target,max_holding_seconds" in text
    assert "short_term_mean_reversion" in text


def test_micro_cycle_grid_search_empty_dataset(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = MicroCycleGridSearchEngine(database, test_config).run(
        scenario="short_term_mean_reversion",
        top=5,
    )

    assert report.total_results == len(MICRO_CYCLE_GRID_TARGETS) * len(MICRO_CYCLE_GRID_MAX_HOLDING_SECONDS)
    assert report.balanced_candidates == []
    assert all(item.cycles_opened == 0 for item in report.top_by_score)
