from paper.models import PaperCycleStatus
from paper.paper_cycle_manager import PaperCycleManager
from paper.paper_exchange import PaperExchange
from paper.paper_portfolio_manager import PaperPortfolioManager


def test_paper_cycle_open_and_close_buy(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0)

    assert cycle is not None
    assert cycle.status == PaperCycleStatus.OPEN
    assert manager.has_active_cycle() is True

    closed = manager.try_close_cycle(1.01)

    assert closed is not None
    assert closed.status == PaperCycleStatus.CLOSED
    assert manager.has_active_cycle() is False


def test_paper_cycle_does_not_close_before_target(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    manager.open_cycle("BUY_USDC", 1.0)
    closed = manager.try_close_cycle(1.0)

    assert closed is None
    assert manager.has_active_cycle() is True


def test_paper_cycle_can_use_decision_target_profit(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    target_profit = test_config.target_profit * 0.25
    cycle = manager.open_cycle("BUY_USDC", 1.0, target_profit=target_profit)

    assert cycle is not None
    assert cycle.close_price == 1.0 * (1 + target_profit)


def test_paper_cycle_close_tolerance_allows_one_tick_short_buy_close(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    target_profit = test_config.target_profit * 0.25
    cycle = manager.open_cycle("BUY_USDC", 1.0, target_profit=target_profit)
    near_target = cycle.close_price - test_config.price_tick_size

    assert manager.can_close_cycle(cycle, near_target) is False
    assert manager.can_close_cycle(
        cycle,
        near_target,
        tolerance=test_config.price_tick_size,
    ) is True


def test_paper_cycle_close_rounding_allows_market_noise_buy_close(test_config):
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0, target_profit=0.00059503)
    current_price = cycle.close_price - 0.00000003

    assert manager.can_close_cycle(cycle, current_price) is False
    assert manager.can_close_cycle(
        cycle,
        current_price,
        rounding_digits=7,
    ) is True
