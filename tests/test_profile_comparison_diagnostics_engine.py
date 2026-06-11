from pathlib import Path

import pytest

from analytics.profile_comparison_diagnostics_engine import ProfileComparisonDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    *,
    price: float,
    work_position: float,
    micro_trend: str,
) -> None:
    timestamp = f"2026-01-01T00:00:{index:02d}"
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
            timestamp,
            "USDCUSDT",
            price,
            price - 0.00001,
            price + 0.00001,
            0.00002,
            price,
            work_position,
            price,
            50.0,
            price,
            50.0,
            "LOW",
            "MIXED",
            80.0,
            "NORMAL",
            0.8,
            0.7,
            0.9,
            0.6,
            0.5,
            0.1,
            "BALANCED",
            micro_trend,
            0.00001,
            "LOW",
            100.0,
            "HEALTHY",
            "OK",
        ),
    )


def test_profile_comparison_counts_profile_variants(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, price=1.0, work_position=25.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 1, price=1.00025, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 2, price=1.0, work_position=70.0, micro_trend="SELL_DOMINANT")
        _insert_snapshot(conn, 3, price=0.99975, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 4, price=1.0, work_position=25.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 5, price=1.00025, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 6, price=1.0, work_position=30.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 7, price=0.9999, work_position=50.0, micro_trend="NEUTRAL")
        conn.commit()

    report = ProfileComparisonDiagnosticsEngine(database, test_config).build_report(horizons=(1, 3))
    by_profile = {item.profile: item for item in report.results}

    assert report.fee_rates.maker == 0.0
    assert report.fee_rates.taker == 0.0
    assert by_profile["mean_reversion_v2"].candidate_count == 1
    assert by_profile["mean_reversion_v3"].candidate_count == 3
    assert by_profile["mean_reversion_v4"].candidate_count == 2
    assert by_profile["mean_reversion_v5"].candidate_count == 4
    assert by_profile["mean_reversion_v5"].buy_count == 3
    assert by_profile["mean_reversion_v5"].sell_count == 1
    assert by_profile["mean_reversion_v5"].target_hit_rates[0].hit_rate == pytest.approx(0.75)


def test_profile_comparison_scores_empty_data(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = ProfileComparisonDiagnosticsEngine(database, test_config).build_report(horizons=(1,))

    assert len(report.results) == 4
    assert all(item.candidate_count == 0 for item in report.results)
    assert all(item.recommendation_score == 0.0 for item in report.results)
