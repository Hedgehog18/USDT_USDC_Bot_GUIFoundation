from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from analytics.trend_strength_diagnostics_engine import (
    TrendStrengthDiagnosticsEngine,
    TrendStrengthItem,
)
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


def test_trend_strength_report_includes_flat_candidate_metrics(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.000000, work_position=50.0, micro_trend="NEUTRAL")
    _insert_snapshot(database, start + timedelta(hours=1), price=0.999960, work_position=20.0, micro_trend="BUY_DOMINANT")
    _insert_snapshot(database, start + timedelta(hours=1, minutes=1), price=1.000020, work_position=50.0, micro_trend="NEUTRAL")

    report = TrendStrengthDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )

    assert len(report.candidates) == 1
    assert report.candidates[0].trend_label == "FLAT"
    assert report.candidates[0].one_hour_change is not None
    assert report.candidates[0].position_inside_range is not None
    assert report.candidates[0].outcome == "hit target"


def test_trend_strength_report_flags_bad_open_buy_when_relabel_blocks(test_config, tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 6, 10, 10, 0, 0)
    _insert_snapshot(database, start, price=1.000000, work_position=50.0, micro_trend="NEUTRAL")
    _insert_snapshot(database, start + timedelta(hours=1), price=0.999960, work_position=20.0, micro_trend="BUY_DOMINANT")

    database.save_paper_cycle(
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=0.999960,
            close_price=1.000010,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=start + timedelta(hours=1),
        ),
        strategy_profile="mean_reversion_v2_small_target",
    )

    report = TrendStrengthDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target"
    )
    by_name = {item.name: item for item in report.simulations}

    assert by_name["flat_as_down_0_005_percent"].bad_open_cycle_blocked is False
    assert report.open_cycles[0].outcome == "open profit"


def test_relabel_flat_trend_uses_percent_threshold(test_config, tmp_path: Path) -> None:
    engine = TrendStrengthDiagnosticsEngine(DatabaseManager(str(tmp_path / "bot.sqlite")), test_config)
    item = TrendStrengthItem(
        source="candidate",
        db_id=None,
        timestamp="2026-06-10T11:00:00",
        direction="BUY_USDC",
        entry_price=1.0,
        comparison_price=0.9999,
        trend_label="FLAT",
        one_hour_change=-0.00006,
        one_hour_change_percent=-0.00006,
        one_hour_slope=-0.000001,
        rolling_min=0.99994,
        rolling_max=1.0,
        position_inside_range=0.0,
        near_top_of_range=False,
        near_bottom_of_range=True,
        outcome="open loss",
    )

    assert engine._relabel_flat_trend(item, "DOWN", -0.00005) == "DOWN"
    assert engine._is_against(item.direction, "DOWN") is True


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
