from datetime import datetime, timedelta
from pathlib import Path

from analytics.high_frequency_snapshot_collector import HighFrequencySnapshotCollector
from market.models import MarketState
from storage.database_manager import DatabaseManager


class FakeAnalyzer:
    last_data_source = "TEST"

    def __init__(self, states: list[MarketState]) -> None:
        self.states = states
        self.index = 0

    def analyze_market(self) -> MarketState:
        state = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return state


def _market_state(**overrides) -> MarketState:
    base = {
        "symbol": "USDCUSDT",
        "price": 1.0001,
        "bid": 1.00009,
        "ask": 1.00011,
        "spread": 0.00002,
        "work_low": 0.9999,
        "work_high": 1.0003,
        "work_center": 1.0001,
        "work_position": 20.0,
        "short_low": 0.9998,
        "short_high": 1.0004,
        "short_center": 1.0001,
        "short_position": 50.0,
        "long_low": 0.9997,
        "long_high": 1.0005,
        "long_center": 1.0001,
        "long_position": 50.0,
        "center_confidence": "LOW",
        "center_alignment": "ALIGNED",
        "tick_activity_score": 10.0,
        "center_crossing_score": 10.0,
        "mean_reversion_score": 10.0,
        "spread_stability_score": 10.0,
        "corridor_quality_score": 10.0,
        "market_activity_score": 50.0,
        "market_regime": "NORMAL",
        "created_at": datetime(2026, 6, 26, 13, 0, 0),
        "order_book_pressure": "BALANCED",
        "micro_trend": "BUY_DOMINANT",
        "volatility_regime": "LOW",
        "market_health_score": 100.0,
        "market_health_status": "HEALTHY",
        "market_health_reason": "OK",
    }
    base.update(overrides)
    return MarketState(**base)


def test_high_frequency_collector_saves_snapshot(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    analyzer = FakeAnalyzer([_market_state()])
    collector = HighFrequencySnapshotCollector(database, test_config, analyzer=analyzer)

    result = collector.collect(duration_hours=0, interval_seconds=5, max_snapshots=1)

    assert result.snapshots_collected == 1
    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT price, mid_price, entry_zone, would_open_cycle, reason_if_not, session, data_source
            FROM market_snapshots_hf
            """
        ).fetchone()

    assert row[0] == 1.0001
    assert row[1] == 1.0001
    assert row[2] == "BUY"
    assert row[3] == 1
    assert row[4] == ""
    assert row[5] == "LONDON_NEW_YORK_OVERLAP"
    assert row[6] == "TEST"


def test_high_frequency_collector_records_block_reason(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    analyzer = FakeAnalyzer([
        _market_state(
            created_at=datetime(2026, 6, 26, 13, 0, 10),
            work_position=50.0,
            micro_trend="NEUTRAL",
        )
    ])
    collector = HighFrequencySnapshotCollector(database, test_config, analyzer=analyzer)

    collector.collect(duration_hours=0, interval_seconds=5, max_snapshots=1)

    with database.connect() as conn:
        row = conn.execute(
            "SELECT entry_zone, would_open_cycle, reason_if_not FROM market_snapshots_hf"
        ).fetchone()

    assert row[0] == "CENTER"
    assert row[1] == 0
    assert row[2] == "entry_zone"


def test_high_frequency_collector_calculates_price_change(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    started = datetime(2026, 6, 26, 13, 0, 0)
    analyzer = FakeAnalyzer([
        _market_state(created_at=started, price=1.0000, bid=0.99999, ask=1.00001),
        _market_state(created_at=started + timedelta(seconds=5), price=1.0002, bid=1.00019, ask=1.00021),
    ])
    collector = HighFrequencySnapshotCollector(database, test_config, analyzer=analyzer)

    collector.collect(duration_hours=1, interval_seconds=0.01, max_snapshots=2)

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT price_change_5_sec
            FROM market_snapshots_hf
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()

    assert round(row[0], 7) == 0.0002
