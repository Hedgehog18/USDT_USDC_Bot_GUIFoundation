import pytest

from analytics.extreme_replay_engine import ExtremeReplayEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    opened_at: str,
    closed_at: str,
    close_price: float = 0.99992000,
    open_price: float = 1.00000000,
    profile: str = "mean_reversion_hf_micro_v1",
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, 'SELL_USDC', 'CLOSED',
                      ?, ?, 10, 0, 0, 0.001, 0.001, ?, ?, 'target')
            """,
            (
                db_id,
                opened_at,
                db_id,
                profile,
                open_price,
                close_price,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'short_center_direct', 2, 4, 0, 'SELL_USDC', 'test')
            """,
            (
                db_id,
                opened_at,
                profile,
                open_price,
                open_price - 0.00001,
                open_price - 0.00001,
                open_price - 0.00002,
            ),
        )
        conn.commit()


def _snapshot(
    timestamp: str,
    *,
    price: float,
    price_change_5_sec: float = 0.0,
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
        "spread": 0.00001,
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


def test_extreme_replay_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    output = tmp_path / "replay.txt"

    report = ExtremeReplayEngine(database).build_report(output_path=output)

    assert report.statistics.events_count == 0
    assert report.statistics.entered_replays_count == 0
    assert report.statistics.assessment == "NEED_MORE_EXTREME_DATA"
    assert output.exists()


def test_extreme_replay_one_event_calculates_excursions(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, opened_at="2026-07-02T10:00:00", closed_at="2026-07-02T10:01:00")
    database.save_hf_market_snapshot(_snapshot("2026-07-02T10:00:00", price=1.00000000))
    database.save_hf_market_snapshot(_snapshot("2026-07-02T10:00:30", price=1.00001000))
    database.save_hf_market_snapshot(_snapshot(
        "2026-07-02T10:00:45",
        price=0.99995000,
        price_change_5_sec=-0.00003,
        distance_to_short_center=0.00006,
    ))
    database.save_hf_market_snapshot(_snapshot("2026-07-02T10:01:00", price=0.99992000))

    report = ExtremeReplayEngine(database).build_report(output_path=tmp_path / "replay.txt")
    event = report.events[0]
    immediate = event.scenarios[0]

    assert event.db_id == 1
    assert event.cluster_label == "Single"
    assert immediate.scenario == "Immediate Entry"
    assert immediate.entered is True
    assert immediate.direction == "SELL_USDC"
    assert immediate.maximum_favorable_excursion == pytest.approx(0.00008)
    assert immediate.maximum_adverse_excursion == pytest.approx(0.00001)
    assert immediate.reward_risk == pytest.approx(8.0)
    assert report.statistics.entered_replays_count >= 1


def test_extreme_replay_multiple_events_and_statistics(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, opened_at="2026-07-02T10:00:00", closed_at="2026-07-02T10:01:00")
    _insert_cycle(database, db_id=2, opened_at="2026-07-02T11:00:00", closed_at="2026-07-02T11:01:00")
    for timestamp in ("2026-07-02T10:00:00", "2026-07-02T11:00:00"):
        database.save_hf_market_snapshot(_snapshot(timestamp, price=1.00000000))
    for timestamp in ("2026-07-02T10:01:00", "2026-07-02T11:01:00"):
        database.save_hf_market_snapshot(_snapshot(timestamp, price=0.99992000))

    report = ExtremeReplayEngine(database).build_report(output_path=tmp_path / "replay.txt")

    assert report.statistics.events_count == 2
    assert report.statistics.scenario_count == 8
    assert report.statistics.average_potential_profit is not None
    assert len(report.events) == 2


def test_extreme_replay_cluster_labels(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, opened_at="2026-07-02T10:00:00", closed_at="2026-07-02T10:01:00")
    _insert_cycle(database, db_id=2, opened_at="2026-07-02T10:04:00", closed_at="2026-07-02T10:05:00")
    _insert_cycle(database, db_id=3, opened_at="2026-07-02T11:00:00", closed_at="2026-07-02T11:01:00")
    for timestamp in (
        "2026-07-02T10:00:00",
        "2026-07-02T10:04:00",
        "2026-07-02T11:00:00",
    ):
        database.save_hf_market_snapshot(_snapshot(timestamp, price=1.00000000))

    report = ExtremeReplayEngine(database).build_report(output_path=tmp_path / "replay.txt")
    labels = {event.db_id: event.cluster_label for event in report.events}

    assert labels[1] == "Double"
    assert labels[2] == "Double"
    assert labels[3] == "Single"
