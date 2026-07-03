from analytics.extreme_signal_leadtime_engine import ExtremeSignalLeadTimeEngine
from storage.database_manager import DatabaseManager


def _insert_extreme_cycle(
    database: DatabaseManager,
    *,
    db_id: int = 1,
    opened_at: str = "2026-07-02T10:00:00",
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


def _snapshot(timestamp: str, *, price: float, session: str = "NEW_YORK") -> dict:
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
        "distance_to_short_center": 0.00002,
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


def _save_snapshots(database: DatabaseManager, rows: list[tuple[str, float, str]]) -> None:
    for timestamp, price, session in rows:
        database.save_hf_market_snapshot(_snapshot(timestamp, price=price, session=session))


def _seed_leadtime_data(database: DatabaseManager) -> None:
    _insert_extreme_cycle(database)
    _save_snapshots(database, [
        ("2026-07-02T10:00:00", 1.00000000, "NEW_YORK"),
        ("2026-07-02T10:02:00", 1.00000000, "NEW_YORK"),
        ("2026-07-02T10:02:25", 1.00000000, "NEW_YORK"),
        ("2026-07-02T10:02:45", 0.99997000, "NEW_YORK"),
        ("2026-07-02T10:02:55", 0.99995000, "NEW_YORK"),
        ("2026-07-02T10:03:00", 0.99992000, "NEW_YORK"),
        ("2026-07-02T10:10:00", 1.00010000, "ASIA"),
        ("2026-07-02T10:10:30", 1.00010000, "ASIA"),
        ("2026-07-02T10:11:00", 1.00010000, "ASIA"),
    ])


def test_extreme_signal_leadtime_calculates_lead_time_results(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _seed_leadtime_data(database)

    report = ExtremeSignalLeadTimeEngine(database).build_report(output_path=tmp_path / "lead.txt")

    velocity_rows = [
        row for row in report.lead_time_results
        if row.signal_name == "velocity_spike_before_extreme"
    ]
    assert velocity_rows
    assert any(row.lead_time_seconds == 5 and row.events_detected >= 1 for row in velocity_rows)


def test_extreme_signal_leadtime_ranks_signals(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _seed_leadtime_data(database)

    report = ExtremeSignalLeadTimeEngine(database).build_report(output_path=tmp_path / "lead.txt")

    assert report.signal_summaries
    assert report.best_signal == report.signal_summaries[0]
    assert report.signal_summaries[0].signal_score >= report.signal_summaries[-1].signal_score


def test_extreme_signal_leadtime_false_positives_are_counted(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _seed_leadtime_data(database)

    report = ExtremeSignalLeadTimeEngine(database).build_report(output_path=tmp_path / "lead.txt")

    session_rows = [
        row for row in report.lead_time_results
        if row.signal_name == "session_specific_signal"
    ]
    assert session_rows
    assert all(row.false_positives >= 0 for row in session_rows)


def test_extreme_signal_leadtime_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = ExtremeSignalLeadTimeEngine(database).build_report(output_path=tmp_path / "lead.txt")

    assert report.extreme_events_analyzed == 0
    assert report.final_recommendation == "NEED_MORE_SIGNAL_DATA"


def test_extreme_signal_leadtime_report_file_saved(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _seed_leadtime_data(database)
    output = tmp_path / "lead.txt"

    report = ExtremeSignalLeadTimeEngine(database).build_report(output_path=output)

    assert output.exists()
    assert "Extreme Signal Lead Time Report" in output.read_text(encoding="utf-8")
    assert report.report_path == str(output)
