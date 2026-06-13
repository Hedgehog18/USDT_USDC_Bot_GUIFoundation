from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from analytics.trend_alignment_diagnostics_engine import TrendAlignmentDiagnosticsEngine
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


def test_trend_alignment_engine_flags_open_cycle_against_1h_trend(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.0010, work_position=50.0, micro_trend="NEUTRAL")
    _insert_snapshot(database, start + timedelta(hours=1), price=1.0000, work_position=20.0, micro_trend="BUY_DOMINANT")
    _insert_snapshot(database, start + timedelta(hours=2), price=0.9990, work_position=20.0, micro_trend="BUY_DOMINANT")

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
            opened_at=start + timedelta(hours=1),
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = TrendAlignmentDiagnosticsEngine(database, test_config).build_alignment_report(
        profile="mean_reversion_v2_small_target",
        current_price=0.9990,
    )

    assert len(report.open_cycles) == 1
    assert report.open_cycles[0].entry_1h_trend == "DOWN"
    assert report.open_cycles[0].entry_against_1h is True
    assert report.open_cycles[0].entry_aligned_with_1h is False


def test_trend_filter_simulation_blocks_against_trend_buy_candidate(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.0010, work_position=50.0, micro_trend="NEUTRAL")
    _insert_snapshot(database, start + timedelta(hours=1), price=1.0000, work_position=20.0, micro_trend="BUY_DOMINANT")

    report = TrendAlignmentDiagnosticsEngine(database, test_config).build_filter_simulation(
        profile="mean_reversion_v2_small_target"
    )
    by_name = {item.name: item for item in report.results}

    assert by_name["no_trend_filter"].candidates_kept == 1
    assert by_name["block_buy_if_1h_down"].candidates_blocked == 1
    assert by_name["require_entry_aligned_with_1h"].candidates_blocked == 1
    assert by_name["soft_block_against_1h"].candidates_blocked == 1
    assert by_name["soft_block_against_1h"].would_block_current_bad_buy_cycle is False


def test_soft_trend_filter_allows_flat_trend_candidate(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.00000, work_position=50.0, micro_trend="NEUTRAL")
    _insert_snapshot(database, start + timedelta(hours=1), price=1.00001, work_position=20.0, micro_trend="BUY_DOMINANT")

    report = TrendAlignmentDiagnosticsEngine(database, test_config).build_filter_simulation(
        profile="mean_reversion_v2_small_target"
    )
    by_name = {item.name: item for item in report.results}

    assert by_name["soft_block_against_1h"].candidates_kept == 1
    assert by_name["soft_block_against_1h"].candidates_blocked == 0
    assert by_name["require_entry_aligned_with_1h"].candidates_blocked == 1


def _insert_snapshot(
    database: DatabaseManager,
    timestamp: datetime,
    *,
    price: float,
    work_position: float,
    micro_trend: str,
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
                price,
                work_position,
                price,
                work_position,
                price,
                work_position,
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
                micro_trend,
                0.0,
                "LOW",
                100.0,
                "HEALTHY",
                "",
            ),
        )
        conn.commit()
