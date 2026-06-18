from datetime import datetime
from pathlib import Path

from analytics.rounding_exit_diagnostics_engine import RoundingExitDiagnosticsEngine
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from storage.database_manager import DatabaseManager


def test_rounding_exit_diagnostics_detects_cycle_that_would_close_earlier(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0,
        close_price=1.00059503,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    database.save_paper_cycle(cycle, strategy_profile="mean_reversion_v2_small_target_r7")

    report = RoundingExitDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target_r7",
        current_price=1.00059500,
        current_price_source="TEST",
        current_price_timestamp="2026-06-11T00:00:00",
    )

    assert report.profile == "mean_reversion_v2_small_target_r7"
    assert report.current_price_source == "TEST"
    assert report.open_cycles_count == 1
    assert report.would_close_earlier_count == 1
    assert report.average_saved_holding_time_seconds >= 0.0
    assert report.profit_difference_vs_strict_comparison < 0.0
    assert report.recommendation_score > 0.0
    item = report.cycles[0]
    assert item.strict_close is False
    assert item.rounded_close is True
    assert item.would_close_earlier is True


def test_rounding_exit_diagnostics_ignores_other_profiles(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0,
        close_price=1.00059503,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    database.save_paper_cycle(cycle, strategy_profile="mean_reversion_v2_small_target")

    report = RoundingExitDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target_r7",
        current_price=1.00059500,
    )

    assert report.open_cycles_count == 0
    assert report.would_close_earlier_count == 0

