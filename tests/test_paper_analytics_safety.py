from paper.models import PaperPortfolio
from paper.paper_analytics_engine import PaperAnalyticsEngine
from paper.paper_safety_engine import PaperSafetyEngine


def test_paper_analytics_from_rows():
    rows = [
        ("t", 1, "BUY_USDC", "CLOSED", 1.0, 1.01, 10.0, 0.01, 0.01, 0.1, 0.08),
        ("t", 2, "BUY_USDC", "CLOSED", 1.0, 0.99, 10.0, 0.01, 0.01, -0.1, -0.12),
    ]

    stats = PaperAnalyticsEngine().build_from_rows(rows)

    assert stats.closed_cycles == 2
    assert stats.winning_cycles == 1
    assert stats.losing_cycles == 1
    assert stats.win_rate == 0.5


def test_paper_safety_blocks_drawdown(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=70.0, usdc=0.0)

    result = engine.check(portfolio, [])

    assert result.allowed is False


def test_paper_safety_allows_normal(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)

    result = engine.check(portfolio, [])

    assert result.allowed is True
