from backtest.equity_analytics_engine import EquityAnalyticsEngine
from backtest.models import BacktestTrade


def test_equity_points():
    points = EquityAnalyticsEngine().build_equity_points([100.0, 101.0])

    assert len(points) == 2
    assert points[0].index == 0
    assert points[1].value == 101.0


def test_period_analytics():
    trade = BacktestTrade(
        index=1,
        action="BUY_USDC",
        entry_price=1.0,
        exit_price=1.001,
        quantity=10.0,
        gross_profit=0.01,
        fees=0.001,
        net_profit=0.009,
    )

    periods = EquityAnalyticsEngine().build_period_analytics(
        equity_curve=[100.0, 101.0, 102.0, 101.0],
        trades=[trade],
        period_size=2,
    )

    assert len(periods) >= 1
    assert periods[0].trades == 1
