from analytics.center_confidence_rule_sim_engine import CenterConfidenceRuleSimulationEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    work_center: float,
    short_center: float,
    long_center: float,
    center_confidence: str,
    order_book_pressure: str,
    micro_trend: str,
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
            0.00001,
            work_center,
            work_position,
            short_center,
            50.0,
            long_center,
            50.0,
            center_confidence,
            "MIXED",
            80.0,
            "NORMAL",
            0.8,
            0.7,
            0.9,
            0.6,
            0.5,
            0.1,
            order_book_pressure,
            micro_trend,
            0.00001,
            "LOW",
            100.0,
            "HEALTHY",
            "OK",
        ),
    )


def test_center_confidence_rule_sim_empty_database(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = CenterConfidenceRuleSimulationEngine(database, test_config).build_report()

    assert len(report.profiles) == 5
    assert report.profiles[0].total_entry_zone_samples == 0
    assert report.profiles[0].pass_count == 0


def test_center_confidence_rule_sim_profiles_keep_other_filters(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(
            conn,
            0,
            10.0,
            1.00030,
            1.00030,
            1.00005,
            "LOW",
            "BID_PRESSURE",
            "BUY_DOMINANT",
        )
        _insert_snapshot(
            conn,
            1,
            85.0,
            1.00030,
            1.00020,
            1.00015,
            "LOW",
            "ASK_PRESSURE",
            "SELL_DOMINANT",
        )
        _insert_snapshot(
            conn,
            2,
            90.0,
            1.00030,
            1.00020,
            1.00010,
            "HIGH",
            "ASK_PRESSURE",
            "SELL_DOMINANT",
        )
        _insert_snapshot(
            conn,
            3,
            15.0,
            1.00030,
            1.00030,
            1.00005,
            "LOW",
            "ASK_PRESSURE",
            "BUY_DOMINANT",
        )
        conn.commit()

    report = CenterConfidenceRuleSimulationEngine(database, test_config).build_report(latest=2)
    profiles = {profile.name: profile for profile in report.profiles}

    assert profiles["strict_current"].pass_count == 1
    assert ("center_confidence", 3) in profiles["strict_current"].remaining_blocking_filters
    assert profiles["allow_mixed_if_work_short_aligned"].pass_count == 2
    assert profiles["tolerate_long_lag_0_0002"].pass_count == 2
    assert profiles["tolerate_long_lag_0_0003"].pass_count == 3
    assert profiles["ignore_long_center_for_entry"].pass_count == 2
    assert ("order_book_pressure", 1) in profiles["ignore_long_center_for_entry"].remaining_blocking_filters
    assert profiles["tolerate_long_lag_0_0003"].buy_candidates == 2
    assert profiles["tolerate_long_lag_0_0003"].sell_candidates == 2
    assert len(profiles["tolerate_long_lag_0_0003"].latest_passed_samples) == 2
