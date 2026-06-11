from datetime import datetime
from pathlib import Path

import pytest

from analytics.holding_horizon_diagnostics_engine import HoldingHorizonDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    *,
    price: float,
    work_position: float,
    micro_trend: str,
) -> str:
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
    return timestamp


def _insert_open_cycle(
    database: DatabaseManager,
    *,
    cycle_id: int,
    profile: str,
    direction: str,
    open_price: float,
    target_price: float,
    opened_at: str | None = None,
) -> None:
    timestamp = opened_at or datetime.now().isoformat()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                cycle_id,
                profile,
                direction,
                "OPEN",
                open_price,
                target_price,
                10.0,
                0.0,
                0.0,
                0.0,
                0.0,
                timestamp,
                None,
            ),
        )
        conn.commit()


def test_holding_horizon_counts_target_hits(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, price=1.0, work_position=25.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 1, price=0.99995, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 2, price=1.0001, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 3, price=1.00025, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 4, price=0.9998, work_position=75.0, micro_trend="SELL_DOMINANT")
        _insert_snapshot(conn, 5, price=0.9997, work_position=50.0, micro_trend="NEUTRAL")
        conn.commit()

    report = HoldingHorizonDiagnosticsEngine(database, test_config).build_report(
        current_price=1.0,
        profile="mean_reversion_v2",
        horizons=(1, 3),
    )

    one, three = report.horizons
    assert one.candidates_count == 2
    assert one.hit_target_count == 0
    assert one.expired_without_target_count == 2
    assert three.candidates_count == 2
    assert three.hit_target_count == 1
    assert three.average_time_to_target == 3
    assert three.max_adverse_movement < 0


def test_holding_horizon_open_cycle_observed_movements(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        opened_at = _insert_snapshot(conn, 0, price=1.0, work_position=25.0, micro_trend="BUY_DOMINANT")
        _insert_snapshot(conn, 1, price=1.0001, work_position=50.0, micro_trend="NEUTRAL")
        _insert_snapshot(conn, 2, price=0.9999, work_position=50.0, micro_trend="NEUTRAL")
        conn.commit()
    _insert_open_cycle(
        database,
        cycle_id=1,
        profile="mean_reversion_v2",
        direction="BUY_USDC",
        open_price=1.0,
        target_price=1.0002,
        opened_at=opened_at,
    )

    report = HoldingHorizonDiagnosticsEngine(database, test_config).build_report(
        current_price=1.00005,
        profile="mean_reversion_v2",
        horizons=(1,),
    )

    item = report.open_cycles[0]
    assert item.max_observed_favorable_movement == pytest.approx(0.0001)
    assert item.max_observed_adverse_movement < 0
    assert item.distance_to_target > 0
