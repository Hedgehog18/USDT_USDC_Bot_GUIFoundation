from pathlib import Path

import pytest

from analytics.post_entry_path_diagnostics_engine import PostEntryPathDiagnosticsEngine
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


def test_post_entry_path_reports_candidate_price_paths(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, price=1.0, work_position=25.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 1, price=1.0001, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 2, price=1.00025, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 3, price=1.0, work_position=75.0, micro_trend="SELL_DOMINANT")
        _insert_snapshot(conn, 4, price=1.0002, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 5, price=1.0003, work_position=50.0, micro_trend="NEUTRAL")
        conn.commit()

    report = PostEntryPathDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2",
        horizons=(1, 3),
    )

    assert len(report.candidates) == 2
    first, second = report.candidates
    assert first.direction == "BUY_USDC"
    assert first.did_hit_target is True
    assert first.did_move_halfway_to_target is True
    assert first.max_favorable_movement == pytest.approx(0.00025)
    assert first.next_prices == [(1, 1.0001), (3, 1.0)]
    assert second.direction == "SELL_USDC"
    assert second.did_hit_target is False
    assert second.did_reverse_against_entry is True
    assert second.failure_mode == "immediate adverse move"
    assert report.summary.candidates_count == 2
    assert report.summary.hit_target_rate == pytest.approx(0.5)
    assert report.summary.halfway_to_target_rate == pytest.approx(0.5)
    assert report.summary.common_failure_mode == "immediate adverse move"


def test_post_entry_path_handles_empty_data(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = PostEntryPathDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2",
        horizons=(1,),
    )

    assert report.candidates == []
    assert report.summary.candidates_count == 0
    assert report.summary.common_failure_mode == "no candidates"
