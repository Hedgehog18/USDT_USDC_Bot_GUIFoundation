from pathlib import Path

from portfolio.bot_budget_manager import BotBudgetManager
from portfolio.portfolio_analytics import PortfolioAnalytics
from storage.database_manager import DatabaseManager


def test_budget_manager_saves_deposits(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    manager = BotBudgetManager(database)

    assert database.count_rows("bot_budget_events") == 2
    assert database.sum_total_deposits() == 100.0


def test_budget_manager_remove_from_budget(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    manager = BotBudgetManager(database)

    manager.remove_from_budget(10.0, "USDT", "test remove")

    assert database.sum_removed_from_budget() == 10.0
    assert database.calculate_net_deposits() == 90.0


def test_portfolio_analytics_uses_net_deposits(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    BotBudgetManager(database)

    analytics = PortfolioAnalytics(database)
    stats = analytics.calculate_stats(current_portfolio_value=100.0)

    assert stats.total_deposits == 100.0
    assert stats.net_deposits == 100.0
