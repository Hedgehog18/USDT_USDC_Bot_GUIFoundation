from paper.models import PaperOrderStatus
from paper.paper_exchange import PaperExchange
from paper.paper_order_manager import PaperOrderManager
from paper.paper_portfolio_manager import PaperPortfolioManager


def test_paper_exchange_buy_fills(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=0.0)
    exchange = PaperExchange(test_config, portfolio)

    result = exchange.execute_market_order("BUY_USDC", price=1.0, quantity=10.0)

    assert result.order.status == PaperOrderStatus.FILLED
    assert result.portfolio.usdc == 10.0
    assert result.portfolio.usdt < 90.0


def test_paper_exchange_rejects_when_not_enough_balance(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=1.0, initial_usdc=0.0)
    exchange = PaperExchange(test_config, portfolio)

    result = exchange.execute_market_order("BUY_USDC", price=1.0, quantity=10.0)

    assert result.order.status == PaperOrderStatus.REJECTED


def test_paper_exchange_sell_fills(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=0.0, initial_usdc=20.0)
    exchange = PaperExchange(test_config, portfolio)

    result = exchange.execute_market_order("SELL_USDC", price=1.0, quantity=10.0)

    assert result.order.status == PaperOrderStatus.FILLED
    assert result.portfolio.usdc == 10.0
    assert result.portfolio.usdt > 9.0
