import pytest

from analytics.strategy_profile_sim_engine import StrategyProfileSimulationEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    center_confidence: str,
    order_book_pressure: str,
    micro_trend: str,
    spread: float = 0.00001,
    market_health_score: float = 100.0,
    market_health_status: str = "HEALTHY",
    market_regime: str = "NORMAL",
    volatility_regime: str = "LOW",
    timestamp: str | None = None,
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
            timestamp or f"2026-01-01T00:0{index}:00",
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            spread,
            1.0003,
            work_position,
            1.0003,
            50.0,
            1.0001,
            50.0,
            center_confidence,
            "MIXED",
            80.0,
            market_regime,
            0.8,
            0.7,
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


def test_strategy_profile_sim_empty_database(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = StrategyProfileSimulationEngine(database, test_config).build_report("mean_reversion_v1")

    assert report.profile == "mean_reversion_v1"
    assert report.total_snapshots == 0
    assert report.pass_count == 0


def test_strategy_profile_sim_mean_reversion_uses_basic_filters_and_micro_trend(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 10.0, "LOW", "ASK_PRESSURE", "BUY_DOMINANT")
        _insert_snapshot(conn, 1, 85.0, "LOW", "BID_PRESSURE", "SELL_DOMINANT")
        _insert_snapshot(conn, 2, 15.0, "LOW", "BID_PRESSURE", "SELL_DOMINANT")
        _insert_snapshot(conn, 3, 90.0, "LOW", "ASK_PRESSURE", "BUY_DOMINANT")
        _insert_snapshot(conn, 4, 50.0, "HIGH", "BID_PRESSURE", "BUY_DOMINANT")
        _insert_snapshot(conn, 5, 12.0, "LOW", "BID_PRESSURE", "BUY_DOMINANT", spread=0.001)
        conn.commit()

    engine = StrategyProfileSimulationEngine(database, test_config)
    strict = engine.build_report("strict_current")
    mean_reversion = engine.build_report("mean_reversion_v1", latest=2)

    assert strict.pass_count == 0
    assert ("center_confidence", 5) in strict.remaining_blocking_filters
    assert mean_reversion.total_snapshots == 6
    assert mean_reversion.total_entry_zone_samples == 5
    assert mean_reversion.pass_count == 2
    assert mean_reversion.buy_candidates == 1
    assert mean_reversion.sell_candidates == 1
    assert ("micro_trend", 2) in mean_reversion.remaining_blocking_filters
    assert ("spread_stability", 1) in mean_reversion.remaining_blocking_filters
    assert [item.direction for item in mean_reversion.latest_candidates] == ["SELL", "BUY"]


def test_strategy_profile_sim_mean_reversion_v2_uses_calibrated_zones(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 25.0, "LOW", "ASK_PRESSURE", "BUY_DOMINANT")
        _insert_snapshot(conn, 1, 75.0, "LOW", "BID_PRESSURE", "SELL_DOMINANT")
        _insert_snapshot(conn, 2, 24.0, "LOW", "BID_PRESSURE", "NEUTRAL")
        _insert_snapshot(conn, 3, 50.0, "HIGH", "BID_PRESSURE", "BUY_DOMINANT")
        conn.commit()

    engine = StrategyProfileSimulationEngine(database, test_config)
    v1 = engine.build_report("mean_reversion_v1")
    v2 = engine.build_report("mean_reversion_v2")
    small_target = engine.build_report("mean_reversion_v2_small_target")

    assert v1.total_entry_zone_samples == 0
    assert v1.pass_count == 0
    assert v2.total_entry_zone_samples == 3
    assert v2.pass_count == 2
    assert v2.buy_candidates == 1
    assert v2.sell_candidates == 1
    assert ("micro_trend", 1) in v2.remaining_blocking_filters
    assert small_target.total_entry_zone_samples == v2.total_entry_zone_samples
    assert small_target.pass_count == v2.pass_count
    assert small_target.buy_candidates == v2.buy_candidates
    assert small_target.sell_candidates == v2.sell_candidates
    tol1 = engine.build_report("mean_reversion_v2_small_target_tol1")
    assert tol1.total_entry_zone_samples == small_target.total_entry_zone_samples
    assert tol1.pass_count == small_target.pass_count
    assert tol1.buy_candidates == small_target.buy_candidates
    assert tol1.sell_candidates == small_target.sell_candidates
    r7 = engine.build_report("mean_reversion_v2_small_target_r7")
    assert r7.total_entry_zone_samples == small_target.total_entry_zone_samples
    assert r7.pass_count == small_target.pass_count
    assert r7.buy_candidates == small_target.buy_candidates
    assert r7.sell_candidates == small_target.sell_candidates
    max12h = engine.build_report("mean_reversion_v2_small_target_max12h")
    assert max12h.total_entry_zone_samples == small_target.total_entry_zone_samples
    assert max12h.pass_count == small_target.pass_count
    assert max12h.buy_candidates == small_target.buy_candidates
    assert max12h.sell_candidates == small_target.sell_candidates


def test_strategy_profile_sim_new_york_profile_filters_by_session(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(
            conn,
            0,
            25.0,
            "LOW",
            "ASK_PRESSURE",
            "BUY_DOMINANT",
            timestamp="2026-01-01T09:00:00",
        )
        _insert_snapshot(
            conn,
            1,
            75.0,
            "LOW",
            "BID_PRESSURE",
            "SELL_DOMINANT",
            timestamp="2026-01-01T18:00:00",
        )
        conn.commit()

    report = StrategyProfileSimulationEngine(database, test_config).build_report(
        "mean_reversion_v2_small_target_ny"
    )

    assert report.total_entry_zone_samples == 2
    assert report.pass_count == 1
    assert report.sell_candidates == 1
    assert ("new_york_session", 1) in report.remaining_blocking_filters


def test_strategy_profile_sim_rejects_unknown_profile(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    with pytest.raises(ValueError):
        StrategyProfileSimulationEngine(database, test_config).build_report("unknown")
