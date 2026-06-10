from types import SimpleNamespace

from analytics.order_book_rule_sim_engine import OrderBookRuleSimulationEngine
from storage.database_manager import DatabaseManager


def _config():
    return SimpleNamespace(
        buy_zone_max=20.0,
        sell_zone_min=80.0,
        max_allowed_spread=0.0002,
        min_market_health_score=50.0,
    )


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    order_book_pressure: str,
    center_confidence: str = "HIGH",
    micro_trend: str = "BUY_DOMINANT",
) -> None:
    conn.execute(
        """
        INSERT INTO market_snapshots (
            timestamp, symbol, price, bid, ask, spread,
            work_center, work_position,
            short_center, short_position,
            long_center, long_position,
            center_confidence, center_alignment,
            market_activity_score, market_regime,
            order_book_pressure, micro_trend, volatility_regime,
            corridor_quality_score, mean_reversion_score,
            market_health_score, market_health_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:0{index}:00",
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            0.0001,
            1.0,
            work_position,
            1.0,
            50.0,
            1.0,
            50.0,
            center_confidence,
            "ALIGNED",
            80.0,
            "NORMAL",
            order_book_pressure,
            micro_trend,
            "NORMAL",
            80.0,
            70.0,
            100.0,
            "HEALTHY",
        ),
    )


def test_order_book_rule_sim_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = OrderBookRuleSimulationEngine(database, _config()).build_report()

    assert [profile.total_entry_zone_samples for profile in report.profiles] == [0, 0, 0, 0]


def test_order_book_rule_sim_compares_profiles(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 10.0, "BID_PRESSURE", micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 1, 15.0, "BALANCED", micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 2, 85.0, "BID_PRESSURE", micro_trend="SELL_DOMINANT")
        _insert_snapshot(conn, 3, 90.0, "ASK_PRESSURE", center_confidence="LOW", micro_trend="SELL_DOMINANT")
        conn.commit()

    report = OrderBookRuleSimulationEngine(database, _config()).build_report()
    profiles = {profile.name: profile for profile in report.profiles}

    assert profiles["strict_current"].total_entry_zone_samples == 4
    assert profiles["strict_current"].buy_candidates == 2
    assert profiles["strict_current"].sell_candidates == 2
    assert profiles["strict_current"].pass_count == 1
    assert profiles["allow_balanced"].pass_count == 2
    assert profiles["contrarian_pressure"].pass_count == 2
    assert profiles["ignore_order_book"].pass_count == 3
    assert ("center_confidence", 1) in profiles["ignore_order_book"].remaining_blocking_filters
