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


def test_classic_paper_safety_blocks_after_three_losing_cycles(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = [_cycle_row(-0.01), _cycle_row(-0.02), _cycle_row(-0.03)]

    result = engine.check(portfolio, rows)

    assert result.allowed is False


def test_hf_paper_safety_does_not_block_after_three_losing_cycles(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = [_cycle_row(-0.01), _cycle_row(-0.02), _cycle_row(-0.03)]

    result = engine.check_for_profile(
        portfolio,
        rows,
        strategy_profile="mean_reversion_hf_micro_v1",
    )

    assert result.allowed is True
    assert result.diagnostics["paper_safety_policy"] == "hf_micro"
    assert result.diagnostics["safety_consecutive_losses"] == "3 / 10"
    assert result.diagnostics["safety_min_cycles_met"] == "no"


def test_hf_paper_safety_blocks_after_ten_consecutive_losses(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = [_cycle_row(-0.001) for _ in range(10)] + [_cycle_row(0.001) for _ in range(20)]

    result = engine.check_for_profile(
        portfolio,
        rows,
        strategy_profile="mean_reversion_hf_micro_v1",
    )

    assert result.allowed is False
    assert "consecutive losses" in result.reason


def test_hf_paper_safety_blocks_on_realized_drawdown(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = []
    for index in range(30):
        rows.append(_cycle_row(-0.0004 if index % 2 == 0 else 0.0))

    result = engine.check_for_profile(
        portfolio,
        rows,
        strategy_profile="mean_reversion_hf_micro_v1",
    )

    assert result.allowed is False
    assert "realized drawdown" in result.reason


def test_hf_paper_safety_blocks_on_timeout_loss_rate(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = []
    for index in range(30):
        if index % 5 == 0:
            rows.append(_cycle_row(0.0002, close_reason="target"))
        else:
            rows.append(_cycle_row(-0.00025, close_reason="max_holding_270s"))

    result = engine.check_for_profile(
        portfolio,
        rows,
        strategy_profile="mean_reversion_hf_micro_v1",
    )

    assert result.allowed is False
    assert "timeout loss rate" in result.reason
    assert result.diagnostics["safety_timeout_loss_rate"] == "80.00%"


def _cycle_row(net_profit: float, close_reason: str = "target") -> tuple:
    return (
        "t",
        1,
        "BUY_USDC",
        "CLOSED",
        1.0,
        1.0,
        10.0,
        0.0,
        0.0,
        net_profit,
        net_profit,
        close_reason,
    )
