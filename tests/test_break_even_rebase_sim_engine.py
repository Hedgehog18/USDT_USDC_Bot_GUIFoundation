from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from analytics.break_even_rebase_sim_engine import BreakEvenRebaseSimulationEngine
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


def test_break_even_rebase_sim_only_affects_targets_outside_range(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.00000)
    _insert_snapshot(database, start + timedelta(minutes=30), price=1.00002)

    database.save_paper_cycle(
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.00000,
            close_price=1.00020,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=start,
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = BreakEvenRebaseSimulationEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )
    by_name = {item.name: item for item in report.scenarios}

    assert by_name["no_rebase"].affected_open_cycles == 0
    assert by_name["break_even_plus_1_tick"].affected_open_cycles == 1
    assert by_name["break_even_plus_1_tick"].would_close_now == 1
    assert by_name["break_even_plus_1_tick"].estimated_realized_pnl > 0


def test_break_even_rebase_sim_reports_avoided_loss_vs_range_edge(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.00000)
    _insert_snapshot(database, start + timedelta(minutes=30), price=0.99995)

    database.save_paper_cycle(
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.00000,
            close_price=1.00020,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=start,
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = BreakEvenRebaseSimulationEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )
    by_name = {item.name: item for item in report.scenarios}

    result = by_name["break_even_plus_0_001_percent"]
    assert result.affected_open_cycles == 1
    assert result.avoided_loss_vs_nearest_range_edge > 0
    assert result.average_distance_to_rebased_target is not None


def _insert_snapshot(database: DatabaseManager, timestamp: datetime, *, price: float) -> None:
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
                price,
                50.0,
                price,
                50.0,
                price,
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
