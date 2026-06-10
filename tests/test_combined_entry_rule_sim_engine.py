from analytics.combined_entry_rule_sim_engine import CombinedEntryRuleSimulationEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    center_confidence: str,
    order_book_pressure: str,
    micro_trend: str,
    work_center: float = 1.00030,
    short_center: float = 1.00030,
    long_center: float = 1.00005,
    corridor_quality_score: float = 0.8,
    mean_reversion_score: float = 0.7,
    spread: float = 0.00001,
    market_health_score: float = 100.0,
    market_health_status: str = "HEALTHY",
    market_regime: str = "NORMAL",
    volatility_regime: str = "LOW",
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
            corridor_quality_score, mean_reversion_score,
            spread_stability_score, center_crossing_score,
            tick_activity_score, order_book_imbalance,
            order_book_pressure, micro_trend,
            relative_volatility, volatility_regime,
            market_health_score, market_health_status, market_health_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:0{index}:00",
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            spread,
            work_center,
            work_position,
            short_center,
            50.0,
            long_center,
            50.0,
            center_confidence,
            "MIXED",
            80.0,
            market_regime,
            corridor_quality_score,
            mean_reversion_score,
            0.9,
            0.6,
            0.5,
            0.1,
            order_book_pressure,
            micro_trend,
            0.00001,
            volatility_regime,
            market_health_score,
            market_health_status,
            "OK",
        ),
    )


def test_combined_entry_rule_sim_empty_database(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = CombinedEntryRuleSimulationEngine(database, test_config).build_report()

    assert len(report.profiles) == 6
    assert report.profiles[0].total_entry_zone_samples == 0
    assert report.profiles[0].pass_count == 0


def test_combined_entry_rule_sim_profiles(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 10.0, "HIGH", "BID_PRESSURE", "BUY_DOMINANT")
        _insert_snapshot(conn, 1, 15.0, "LOW", "BID_PRESSURE", "BUY_DOMINANT")
        _insert_snapshot(conn, 2, 85.0, "HIGH", "BALANCED", "SELL_DOMINANT")
        _insert_snapshot(conn, 3, 90.0, "LOW", "BALANCED", "SELL_DOMINANT")
        _insert_snapshot(conn, 4, 88.0, "LOW", "BID_PRESSURE", "SELL_DOMINANT")
        _insert_snapshot(
            conn,
            5,
            12.0,
            "LOW",
            "ASK_PRESSURE",
            "BUY_DOMINANT",
            corridor_quality_score=0.0,
            mean_reversion_score=0.0,
        )
        conn.commit()

    report = CombinedEntryRuleSimulationEngine(database, test_config).build_report(latest=3)
    profiles = {profile.name: profile for profile in report.profiles}

    assert profiles["strict_current"].pass_count == 1
    assert profiles["relaxed_center_only"].pass_count == 2
    assert profiles["relaxed_order_book_only"].pass_count == 2
    assert profiles["relaxed_center_and_balanced"].pass_count == 4
    assert profiles["relaxed_center_ignore_order_book"].pass_count == 5
    assert profiles["entry_zone_only"].pass_count == 6
    assert profiles["strict_current"].buy_candidates == 3
    assert profiles["strict_current"].sell_candidates == 3
    assert ("center_confidence", 4) in profiles["strict_current"].remaining_blocking_filters
    assert ("order_book_pressure", 4) in profiles["strict_current"].remaining_blocking_filters
    assert profiles["entry_zone_only"].remaining_blocking_filters == []
    assert len(profiles["relaxed_center_ignore_order_book"].latest_passed_samples) == 3
