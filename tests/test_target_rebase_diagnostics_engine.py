from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from analytics.target_rebase_diagnostics_engine import TargetRebaseDiagnosticsEngine
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


def test_target_rebase_diagnostics_suggests_range_edge_for_outside_buy_target(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.0000, work_center=1.0000)
    _insert_snapshot(database, start + timedelta(minutes=30), price=1.0001, work_center=1.0000)

    database.save_paper_cycle(
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.0000,
            close_price=1.0002,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=start,
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = TargetRebaseDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )

    item = report.open_cycles[0]
    assert item.target_outside_1h_range is True
    assert item.suggested_rebased_target == 1.0001
    assert item.would_close_if_rebased_now is True

    by_name = {scenario.name: scenario for scenario in report.scenarios}
    assert by_name["rebase_to_nearest_realistic_range_edge"].affected_cycles == 1
    assert by_name["rebase_to_nearest_realistic_range_edge"].would_close_now == 1


def test_target_rebase_break_even_plus_tick_uses_price_tick(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.0000, work_center=1.0000)
    _insert_snapshot(database, start + timedelta(minutes=30), price=1.00002, work_center=1.0000)

    database.save_paper_cycle(
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.0000,
            close_price=1.0002,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=start,
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = TargetRebaseDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )
    by_name = {scenario.name: scenario for scenario in report.scenarios}

    result = by_name["rebase_to_break_even_plus_min_profit"]
    assert result.affected_cycles == 1
    assert result.would_close_now == 1
    assert result.estimated_pnl > 0


def _insert_snapshot(
    database: DatabaseManager,
    timestamp: datetime,
    *,
    price: float,
    work_center: float,
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
                work_center,
                50.0,
                work_center,
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
