import pytest

from analytics.extreme_signal_discovery_engine import ExtremeSignalDiscoveryEngine
from storage.database_manager import DatabaseManager


def _insert_extreme_cycle(
    database: DatabaseManager,
    *,
    db_id: int = 1,
    opened_at: str = "2026-07-02T10:02:00",
    closed_at: str = "2026-07-02T10:03:00",
    close_price: float = 0.99992000,
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, 'mean_reversion_hf_micro_v1', 'SELL_USDC', 'CLOSED',
                      1.0000, ?, 10, 0, 0, 0.001, 0.001, ?, ?, 'target')
            """,
            (db_id, opened_at, db_id, close_price, opened_at, closed_at),
        )
        conn.commit()


def _snapshot(
    timestamp: str,
    *,
    price: float,
    spread: float = 0.00001,
    distance_to_short_center: float = 0.00001,
    session: str = "NEW_YORK",
) -> dict:
    return {
        "timestamp": timestamp,
        "symbol": "USDCUSDT",
        "price": price,
        "bid": price - 0.000005,
        "ask": price + 0.000005,
        "mid_price": price,
        "spread": spread,
        "work_position": 50.0,
        "micro_trend": "NEUTRAL",
        "entry_zone": "CENTER",
        "buy_zone": 0,
        "sell_zone": 0,
        "volatility_regime": "NORMAL",
        "market_regime": "NORMAL",
        "distance_to_long_center": 0.0,
        "distance_to_short_center": distance_to_short_center,
        "distance_to_work_center": 0.0,
        "order_book_pressure": "BALANCED",
        "session": session,
        "price_change_5_sec": 0.0,
        "price_change_10_sec": 0.0,
        "price_change_30_sec": 0.0,
        "price_change_1_min": 0.0,
        "price_change_5_min": 0.0,
        "would_open_cycle": 0,
        "reason_if_not": "test",
        "data_source": "BINANCE",
    }


def _save_snapshots(database: DatabaseManager, rows: list[tuple[str, float]]) -> None:
    for timestamp, price in rows:
        database.save_hf_market_snapshot(_snapshot(timestamp, price=price))


def test_extreme_signal_discovery_builds_pre_event_windows(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_extreme_cycle(database)
    _save_snapshots(database, [
        ("2026-07-02T10:00:00", 1.00000000),
        ("2026-07-02T10:01:00", 1.00000000),
        ("2026-07-02T10:01:45", 1.00000000),
        ("2026-07-02T10:02:00", 1.00001000),
        ("2026-07-02T10:02:55", 1.00001000),
        ("2026-07-02T10:03:00", 0.99992000),
    ])
    engine = ExtremeSignalDiscoveryEngine(database)
    events = engine.discovery.build_report().events
    snapshots = engine._load_hf_snapshots()

    windows = engine._build_pre_event_windows(events, snapshots)

    assert {window.window_seconds for window in windows} == {5, 15, 30, 60, 120}
    assert all(window.event_id == 1 for window in windows)
    assert windows[0].session == "NEW_YORK"


def test_extreme_signal_discovery_builds_control_windows(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_extreme_cycle(database)
    _save_snapshots(database, [
        ("2026-07-02T10:02:00", 1.00000000),
        ("2026-07-02T10:10:00", 1.00010000),
        ("2026-07-02T10:10:30", 1.00011000),
        ("2026-07-02T10:11:00", 1.00012000),
    ])
    engine = ExtremeSignalDiscoveryEngine(database)
    events = engine.discovery.build_report().events
    snapshots = engine._load_hf_snapshots()

    controls = engine._build_control_windows(events, snapshots)

    assert controls
    assert all(control.event_id is None for control in controls)


def test_extreme_signal_discovery_compression_score_calculated(tmp_path):
    engine = ExtremeSignalDiscoveryEngine(DatabaseManager(str(tmp_path / "bot.sqlite")))

    compressed = engine._compression_score(0.0, unique_values=1, samples_count=10, spread=0.00001)
    loose = engine._compression_score(0.00010, unique_values=10, samples_count=10, spread=0.00001)

    assert compressed is not None
    assert loose is not None
    assert compressed > loose
    assert compressed >= 60.0


def test_extreme_signal_discovery_signal_candidate_scoring_and_false_positive(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_extreme_cycle(database)
    _save_snapshots(database, [
        ("2026-07-02T10:00:00", 1.00000000),
        ("2026-07-02T10:01:00", 1.00000000),
        ("2026-07-02T10:02:00", 1.00000000),
        ("2026-07-02T10:02:55", 1.00000000),
        ("2026-07-02T10:03:00", 0.99992000),
        ("2026-07-02T10:10:00", 1.00000000),
        ("2026-07-02T10:10:30", 1.00003000),
        ("2026-07-02T10:11:00", 1.00006000),
    ])
    engine = ExtremeSignalDiscoveryEngine(database)

    report = engine.build_report(output_path=tmp_path / "signal.txt")
    compression = next(candidate for candidate in report.signal_candidates if candidate.name == "compression_before_extreme")

    assert compression.extreme_events_covered >= 1
    assert compression.precision_estimate >= 0.0
    assert compression.false_positive_count >= 0
    assert compression.signal_score >= 0.0


def test_extreme_signal_discovery_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = ExtremeSignalDiscoveryEngine(database).build_report(output_path=tmp_path / "signal.txt")

    assert report.extreme_events_analyzed == 0
    assert report.control_windows_analyzed == 0
    assert report.recommendation == "NEED_MORE_DATA"


def test_extreme_signal_discovery_report_file_saved(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_extreme_cycle(database)
    _save_snapshots(database, [
        ("2026-07-02T10:00:00", 1.00000000),
        ("2026-07-02T10:01:00", 1.00000000),
        ("2026-07-02T10:02:00", 1.00001000),
        ("2026-07-02T10:02:55", 1.00001000),
        ("2026-07-02T10:03:00", 0.99992000),
        ("2026-07-02T10:10:00", 1.00010000),
        ("2026-07-02T10:10:30", 1.00011000),
    ])
    output = tmp_path / "signal.txt"

    report = ExtremeSignalDiscoveryEngine(database).build_report(output_path=output)

    assert output.exists()
    assert "Extreme Signal Discovery Report" in output.read_text(encoding="utf-8")
    assert report.report_path == str(output)
