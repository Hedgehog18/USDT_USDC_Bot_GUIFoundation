from datetime import datetime
from pathlib import Path

from analytics.statistics_engine import StatisticsEngine
from storage.database_manager import DatabaseManager
from strategy.models import RiskResult, TradeDecision
from trading.cycle_manager import CycleManager


def test_statistics_engine_builds_summary(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    cycle_manager = CycleManager()
    cycle = cycle_manager.create_cycle("DEMO", "BUY_USDC", 1.0, 10.0, 0.0002)
    cycle_manager.place_open_order(cycle)
    cycle_manager.mark_open_filled(cycle)
    cycle_manager.place_close_order(cycle)
    cycle_manager.mark_close_filled(cycle)
    database.save_cycle(cycle)

    decision = TradeDecision(
        action="BUY_USDC",
        reason="test",
        confidence="HIGH",
        cycle_prediction_score=80.0,
        recommended_trade_size=10.0,
        target_profit=0.0002,
        created_at=datetime.utcnow(),
    )
    risk = RiskResult(allowed=True, reason="ok", risk_level="LOW")
    database.save_trade_signal(decision, risk, cycle_id=cycle.id)

    engine = StatisticsEngine(database)
    summary = engine.build_summary()

    assert summary.cycle_stats.total_cycles == 1
    assert summary.cycle_stats.closed_cycles == 1
    assert summary.cycle_stats.winning_cycles == 1
    assert summary.signal_stats.total_signals == 1
    assert summary.signal_stats.buy_signals == 1
    assert summary.signal_stats.allowed_signals == 1
    assert summary.signal_stats.average_cycle_prediction_score == 80.0
