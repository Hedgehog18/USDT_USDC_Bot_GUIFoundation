from pathlib import Path

from portfolio.portfolio_analytics import PortfolioAnalytics
from storage.database_manager import DatabaseManager
from trading.cycle_manager import CycleManager


def test_portfolio_analytics_counts_closed_cycle(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    manager = CycleManager()

    cycle = manager.create_cycle("DEMO", "BUY_USDC", 1.0, 10.0, 0.0002)
    manager.place_open_order(cycle)
    manager.mark_open_filled(cycle)
    manager.place_close_order(cycle)
    manager.mark_close_filled(cycle)

    database.save_cycle(cycle)

    analytics = PortfolioAnalytics(database)
    database.save_bot_budget_event(
        __import__("portfolio.models", fromlist=["BotBudgetEvent"]).BotBudgetEvent(
            event_type="DEPOSIT",
            asset="USDT",
            amount=100.0,
            value_usdt=100.0,
            note="test",
            created_at=__import__("datetime").datetime.utcnow(),
        )
    )

    stats = analytics.calculate_stats(
        current_portfolio_value=100.0 + database.sum_realized_profit(),
    )

    assert stats.total_cycles == 1
    assert stats.closed_cycles == 1
    assert stats.winning_cycles == 1
    assert stats.realized_profit > 0
    assert stats.win_rate == 1.0
    assert stats.roi > 0
