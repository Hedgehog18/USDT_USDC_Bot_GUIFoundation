import pytest

from analytics.extreme_market_discovery_engine import ExtremeMarketDiscoveryEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    opened_at: str,
    closed_at: str,
    close_price: float = 0.99992000,
    profile: str = "mean_reversion_hf_micro_v1",
    net_profit: float = 0.001,
    current_price: float = 1.0000,
    previous_price: float = 0.99999,
    last_different_price: float = 0.99998,
    flat_samples_count: int = 3,
    price_buffer_unique_values: int = 2,
    short_center: float = 0.99995,
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, 'SELL_USDC', 'CLOSED',
                      1.0000, ?, 10, 0, 0, ?, ?, ?, ?, 'target')
            """,
            (
                db_id,
                opened_at,
                db_id,
                profile,
                close_price,
                net_profit,
                net_profit,
                opened_at,
                closed_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO hf_paper_cycle_entry_diagnostics (
                paper_cycle_id, timestamp, strategy_profile, current_price,
                short_center, previous_price, last_different_price,
                hf_entry_mode, price_buffer_unique_values, flat_samples_count,
                flat_price_buffer, entry_direction, entry_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'short_center_direct', ?, ?, 0, 'SELL_USDC', 'test')
            """,
            (
                db_id,
                opened_at,
                profile,
                current_price,
                short_center,
                previous_price,
                last_different_price,
                price_buffer_unique_values,
                flat_samples_count,
            ),
        )
        conn.commit()


def _snapshot(
    timestamp: str,
    *,
    price: float = 1.0000,
    spread: float = 0.00001,
    distance_to_short_center: float = 0.00001,
    price_change_5_sec: float = 0.0,
    session: str = "LONDON",
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
        "price_change_5_sec": price_change_5_sec,
        "price_change_10_sec": price_change_5_sec,
        "price_change_30_sec": price_change_5_sec,
        "price_change_1_min": price_change_5_sec,
        "price_change_5_min": price_change_5_sec,
        "would_open_cycle": 0,
        "reason_if_not": "test",
        "data_source": "BINANCE",
    }


def test_extreme_market_discovery_detects_events_duration_sessions_and_stats(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, opened_at="2026-07-02T10:00:00", closed_at="2026-07-02T10:01:00")
    _insert_cycle(database, db_id=2, opened_at="2026-07-02T10:04:00", closed_at="2026-07-02T10:05:00")
    _insert_cycle(database, db_id=3, opened_at="2026-07-02T18:00:00", closed_at="2026-07-02T18:03:00")
    _insert_cycle(database, db_id=4, opened_at="2026-07-02T19:00:00", closed_at="2026-07-02T19:01:00", close_price=1.0001)
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T10:00:30",
        distance_to_short_center=0.00025,
        price_change_5_sec=0.00004,
        session="LONDON",
    ))
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T10:02:00",
        distance_to_short_center=0.00001,
        price_change_5_sec=0.0,
        session="LONDON",
    ))
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T10:05:00",
        distance_to_short_center=0.00010,
        price_change_5_sec=-0.00003,
        session="LONDON",
    ))
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T18:03:00",
        distance_to_short_center=0.00003,
        price_change_5_sec=0.00001,
        session="NEW_YORK",
    ))

    report = ExtremeMarketDiscoveryEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.count == 3
    assert report.average_duration_seconds == pytest.approx(100.0)
    assert report.median_duration_seconds == pytest.approx(60.0)
    assert report.longest_duration_seconds == pytest.approx(180.0)
    assert report.shortest_duration_seconds == pytest.approx(60.0)
    assert report.by_amplitude["Large Extreme"] == 1
    assert report.by_session["LONDON"] == 2
    assert report.by_session["NEW_YORK"] == 1
    assert report.by_hour[10] == 2
    assert report.average_events_per_day == pytest.approx(3.0)
    assert report.maximum_events_per_day == 3
    assert report.minimum_events_per_day == 3


def test_extreme_market_discovery_clustering_and_recovery(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, opened_at="2026-07-02T10:00:00", closed_at="2026-07-02T10:01:00")
    _insert_cycle(database, db_id=2, opened_at="2026-07-02T10:04:00", closed_at="2026-07-02T10:05:00")
    _insert_cycle(database, db_id=3, opened_at="2026-07-02T11:00:00", closed_at="2026-07-02T11:01:00")
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T10:01:30",
        distance_to_short_center=0.00001,
        price_change_5_sec=0.0,
    ))
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T10:05:30",
        distance_to_short_center=0.00001,
        price_change_5_sec=0.0,
    ))
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T11:01:30",
        distance_to_short_center=0.00001,
        price_change_5_sec=0.0,
    ))

    report = ExtremeMarketDiscoveryEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.cluster_distribution["Double"] == 1
    assert report.cluster_distribution["Single"] == 1
    assert report.events[0].recovery_seconds == pytest.approx(30.0)
    assert report.average_recovery_seconds == pytest.approx(30.0)


def test_extreme_market_discovery_pre_context_and_recommendation(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    for db_id in range(1, 22):
        _insert_cycle(
            database,
            db_id=db_id,
            opened_at=f"2026-07-02T10:{db_id:02d}:00",
            closed_at=f"2026-07-02T10:{db_id:02d}:30",
            current_price=1.00004,
            previous_price=1.00000,
            last_different_price=1.00000,
            flat_samples_count=2,
            price_buffer_unique_values=4,
            short_center=1.00000,
        )

    report = ExtremeMarketDiscoveryEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.average_pre_price_velocity == pytest.approx(0.00004)
    assert report.average_pre_short_term_drift == pytest.approx(0.00004)
    assert report.average_pre_flat_samples_count == pytest.approx(2.0)
    assert report.average_pre_buffer_unique_values == pytest.approx(4.0)
    assert report.average_pre_short_center_distance == pytest.approx(0.00004)
    assert report.conclusion == "Extreme events most often appear after a velocity spike."
    assert report.recommendation == "READY_FOR_EXTREME_REPLAY"


def test_extreme_market_discovery_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = ExtremeMarketDiscoveryEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.count == 0
    assert report.average_duration_seconds is None
    assert report.by_session == {}
    assert report.cluster_distribution == {}
    assert report.recommendation == "NEED_MORE_EXTREME_DATA"
