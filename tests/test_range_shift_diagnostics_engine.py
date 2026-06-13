from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from analytics.range_shift_diagnostics_engine import RangeShiftDiagnosticsEngine
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


def test_range_shift_diagnostics_flags_open_cycle_after_center_shift(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.0000, work_center=1.0000, short_center=1.0000, long_center=1.0000)
    _insert_snapshot(database, start + timedelta(hours=2), price=0.9997, work_center=0.9997, short_center=0.9997, long_center=0.9998)

    database.save_paper_cycle(
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.0000,
            close_price=1.00005,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=start,
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = RangeShiftDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )

    assert len(report.open_cycles) == 1
    item = report.open_cycles[0]
    assert item.center_shift_direction == "DOWN"
    assert item.center_shift_percent is not None
    assert item.center_shift_percent > 0.0002
    assert item.target_outside_current_work_range is True
    assert item.open_price_no_longer_realistic_mean_reversion_target is True
    assert report.threshold_simulations[0].stale_open_cycles == 1


def test_range_shift_diagnostics_summarizes_successful_closed_cycles(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.0000, work_center=1.0000, short_center=1.0000, long_center=1.0000)
    _insert_snapshot(database, start + timedelta(minutes=10), price=1.0001, work_center=1.0001, short_center=1.0001, long_center=1.0000)

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
                (start + timedelta(minutes=10)).isoformat(),
                1,
                "mean_reversion_v2_small_target",
                "BUY_USDC",
                "CLOSED",
                1.0,
                1.00005,
                10.0,
                0.0,
                0.0,
                0.0005,
                0.0005,
                start.isoformat(),
                (start + timedelta(minutes=10)).isoformat(),
            ),
        )
        conn.commit()

    report = RangeShiftDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )

    assert report.closed_summary.closed_cycles_count == 1
    assert report.closed_summary.average_center_shift_to_close == pytest.approx(0.0001)
    assert report.closed_summary.successful_average_center_shift == pytest.approx(0.0001)
    assert report.closed_summary.center_shift_distribution


def _insert_snapshot(
    database: DatabaseManager,
    timestamp: datetime,
    *,
    price: float,
    work_center: float,
    short_center: float,
    long_center: float,
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO market_snapshots (
                timestamp, symbol, price, bid, ask, spread,
                work_center, work_position,
                short_center, short_position,
                long_center, long_position,
                center_confidence, center_alignment,
                tick_activity_score, center_crossing_score,
                mean_reversion_score, spread_stability_score,
                corridor_quality_score, market_activity_score,
                market_regime, order_book_imbalance, order_book_pressure,
                trade_volume_delta, micro_trend, relative_volatility,
                volatility_regime, market_health_score, market_health_status,
                market_health_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                "USDCUSDT",
                price,
                price - 0.000005,
                price + 0.000005,
                0.00001,
                work_center,
                50.0,
                short_center,
                50.0,
                long_center,
                50.0,
                "LOW",
                "ALIGNED",
                0.0,
                0.0,
                0.0,
                1.0,
                1.0,
                50.0,
                "NORMAL",
                0.0,
                "BALANCED",
                0.0,
                "NEUTRAL",
                0.0,
                "LOW",
                100.0,
                "HEALTHY",
                "",
            ),
        )
        conn.commit()
