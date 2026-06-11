from pathlib import Path

import pytest

from analytics.entry_confirmation_diagnostics_engine import EntryConfirmationDiagnosticsEngine
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


def test_entry_confirmation_compares_confirmation_variants(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, price=1.0, work_position=25.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 1, price=1.0001, work_position=50.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 2, price=1.00035, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 3, price=1.0, work_position=75.0, micro_trend="SELL_DOMINANT")
        _insert_snapshot(conn, 4, price=1.0002, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 5, price=1.0003, work_position=50.0, micro_trend="NEUTRAL")
        conn.commit()

    report = EntryConfirmationDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2",
        horizon=3,
    )
    by_variant = {item.variant: item for item in report.results}

    immediate = by_variant["immediate_entry"]
    price_turn = by_variant["require_price_turn"]
    persistence = by_variant["require_micro_trend_persistence"]

    assert immediate.base_candidate_count == 2
    assert immediate.candidate_count == 2
    assert immediate.hit_target_rate == pytest.approx(0.5)
    assert immediate.immediate_adverse_move_rate == pytest.approx(0.5)
    assert price_turn.candidate_count == 1
    assert price_turn.missed_opportunities_count == 1
    assert price_turn.hit_target_rate == pytest.approx(1.0)
    assert persistence.candidate_count == 1
    assert persistence.missed_opportunities_count == 1


def test_entry_confirmation_handles_empty_data(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = EntryConfirmationDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2",
        horizon=3,
    )

    assert len(report.results) == 5
    assert all(item.candidate_count == 0 for item in report.results)
    assert all(item.recommendation_score == 0.0 for item in report.results)
