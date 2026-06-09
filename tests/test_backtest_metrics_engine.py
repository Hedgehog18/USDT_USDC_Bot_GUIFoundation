from backtest.backtest_metrics_engine import BacktestMetricsEngine
from backtest.models import BacktestTrade


def make_trade(net_profit: float) -> BacktestTrade:
    return BacktestTrade(
        index=1,
        action="BUY_USDC",
        entry_price=1.0,
        exit_price=1.001,
        quantity=10.0,
        gross_profit=net_profit,
        fees=0.0,
        net_profit=net_profit,
    )


def test_backtest_metrics_engine_calculates_profit_factor_and_expectancy():
    trades = [make_trade(1.0), make_trade(-0.5), make_trade(0.5)]
    equity = [100.0, 101.0, 100.5, 101.0]

    metrics = BacktestMetricsEngine().calculate(trades, equity)

    assert metrics.profit_factor == 3.0
    assert round(metrics.expectancy, 6) == round((1.0 - 0.5 + 0.5) / 3, 6)
    assert len(metrics.returns) == 3


def test_backtest_metrics_engine_handles_empty_data():
    metrics = BacktestMetricsEngine().calculate([], [100.0])

    assert metrics.sharpe_ratio == 0.0
    assert metrics.sortino_ratio == 0.0
    assert metrics.profit_factor == 0.0
    assert metrics.expectancy == 0.0
