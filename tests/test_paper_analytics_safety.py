import pytest

from paper.models import PaperPortfolio
from paper.paper_analytics_engine import PaperAnalyticsEngine
from paper.paper_safety_engine import PaperSafetyEngine


def test_paper_analytics_from_rows():
    rows = [
        ("t", 1, "BUY_USDC", "CLOSED", 1.0, 1.01, 10.0, 0.01, 0.01, 0.1, 0.08, "target"),
        ("t", 2, "BUY_USDC", "CLOSED", 1.0, 0.99, 10.0, 0.01, 0.01, -0.1, -0.12, "max_holding_270s"),
        ("t", 3, "SELL_USDC", "CLOSED", 1.0, 1.0, 10.0, 0.0, 0.0, 0.0, 0.0, "max_holding_270s"),
    ]

    stats = PaperAnalyticsEngine().build_from_rows(rows)

    assert stats.closed_cycles == 3
    assert stats.winning_cycles == 1
    assert stats.breakeven_cycles == 1
    assert stats.losing_cycles == 1
    assert stats.win_rate == pytest.approx(1 / 3)
    assert stats.average_profit == pytest.approx(0.08)
    assert stats.average_loss == pytest.approx(-0.12)
    assert stats.average_cycle_pnl == pytest.approx((0.08 - 0.12) / 3)
    assert stats.expectancy == pytest.approx((1 / 3 * 0.08) + (1 / 3 * -0.12))
    assert stats.timeout_closed == 2
    assert stats.timeout_profit_cycles == 0
    assert stats.timeout_breakeven_cycles == 1
    assert stats.timeout_loss_cycles == 1
    assert stats.timeout_average_pnl == pytest.approx(-0.06)
    assert stats.timeout_max_loss == pytest.approx(-0.12)
    assert stats.target_closed == 1
    assert stats.target_total_profit == pytest.approx(0.08)
    assert stats.buy_count == 2
    assert stats.buy_total_pnl == pytest.approx(-0.04)
    assert stats.sell_count == 1
    assert stats.sell_win_rate == 0.0


def test_paper_analytics_counts_profile_target_reasons():
    rows = [
        ("t", 1, "SELL_USDC", "CLOSED", 1.0, 0.9999, 10.0, 0.0, 0.0, 0.001, 0.001, "extreme_target"),
    ]

    stats = PaperAnalyticsEngine().build_from_rows(rows)

    assert stats.target_closed == 1
    assert stats.target_total_profit == pytest.approx(0.001)


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


def test_extreme_paper_safety_uses_own_policy_and_min_sample(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = [_cycle_row(-0.01), _cycle_row(-0.02), _cycle_row(-0.03)]

    result = engine.check_for_profile(
        portfolio,
        rows,
        strategy_profile="extreme_strategy_v1",
    )

    assert result.allowed is True
    assert result.diagnostics["paper_safety_policy"] == "extreme_v1"
    assert result.diagnostics["safety_min_cycles_met"] == "no"


def test_extreme_paper_safety_blocks_after_five_consecutive_losses(test_config):
    engine = PaperSafetyEngine(test_config)
    portfolio = PaperPortfolio(usdt=100.0, usdc=0.0)
    rows = [_cycle_row(-0.0001) for _ in range(5)] + [_cycle_row(0.0001) for _ in range(5)]

    result = engine.check_for_profile(
        portfolio,
        rows,
        strategy_profile="extreme_strategy_v1",
    )

    assert result.allowed is False
    assert "consecutive losses" in result.reason


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
