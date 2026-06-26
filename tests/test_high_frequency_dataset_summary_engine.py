from pathlib import Path

from analytics.high_frequency_dataset_summary_engine import HighFrequencyDatasetSummaryEngine
from storage.database_manager import DatabaseManager


def _snapshot(**overrides) -> dict:
    base = {
        "timestamp": "2026-06-26T13:00:00",
        "symbol": "USDCUSDT",
        "price": 1.0001,
        "bid": 1.00009,
        "ask": 1.00011,
        "mid_price": 1.0001,
        "spread": 0.00002,
        "work_position": 20.0,
        "micro_trend": "BUY_DOMINANT",
        "entry_zone": "BUY",
        "buy_zone": True,
        "sell_zone": False,
        "volatility_regime": "LOW",
        "market_regime": "NORMAL",
        "distance_to_long_center": 0.0,
        "distance_to_short_center": 0.0,
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


def test_high_frequency_dataset_summary_empty(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = HighFrequencyDatasetSummaryEngine(database).build_summary()

    assert summary.total_snapshots == 0
    assert summary.potential_micro_entries == 0
    assert summary.potential_micro_entry_rate == 0.0


def test_high_frequency_dataset_summary_counts_distributions(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    database.save_hf_market_snapshot(_snapshot())
    database.save_hf_market_snapshot(_snapshot(
        timestamp="2026-06-26T18:00:00",
        work_position=50.0,
        micro_trend="NEUTRAL",
        entry_zone="CENTER",
        buy_zone=False,
        session="NEW_YORK",
        would_open_cycle=False,
        reason_if_not="entry_zone",
    ))

    summary = HighFrequencyDatasetSummaryEngine(database).build_summary()

    assert summary.total_snapshots == 2
    assert summary.potential_micro_entries == 1
    assert ("would_open_cycle", 1) in summary.blockers
    assert ("entry_zone", 1) in summary.blockers
    assert ("LONDON_NEW_YORK_OVERLAP", 1) in summary.by_session
    assert ("NEW_YORK", 1) in summary.by_session
