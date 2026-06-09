from pathlib import Path

from paper.paper_exchange import PaperExchange
from paper.paper_portfolio_manager import PaperPortfolioManager
from storage.database_manager import DatabaseManager


def test_database_saves_paper_execution(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=0.0)
    exchange = PaperExchange(test_config, portfolio)

    execution = exchange.execute_market_order("BUY_USDC", price=1.0, quantity=10.0)
    row_id = database.save_paper_execution(execution)

    assert row_id > 0
    assert database.count_rows("paper_orders") == 1
