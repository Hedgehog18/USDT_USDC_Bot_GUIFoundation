from pathlib import Path

from paper.paper_cycle_manager import PaperCycleManager
from paper.paper_exchange import PaperExchange
from paper.paper_portfolio_manager import PaperPortfolioManager
from storage.database_manager import DatabaseManager


def test_database_saves_paper_cycle(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0)
    row_id = database.save_paper_cycle(cycle)

    assert row_id > 0
    assert database.count_rows("paper_cycles") == 1
