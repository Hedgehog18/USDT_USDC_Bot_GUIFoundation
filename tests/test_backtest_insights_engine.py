from backtest.backtest_insights_engine import BacktestInsightsEngine
from backtest.models import BacktestResult, PeriodAnalytics


def make_result(**overrides):
    data = dict(
        symbol="USDCUSDT",
        interval="1m",
        candles=500,
        signals=20,
        trades=10,
        winning_trades=7,
        losing_trades=3,
        win_rate=0.7,
        gross_profit=2.0,
        total_fees=0.2,
        net_profit=1.8,
        roi=0.018,
        final_value=101.8,
        max_drawdown=0.01,
        sharpe_ratio=0.8,
        sortino_ratio=1.0,
        profit_factor=2.0,
        expectancy=0.18,
    )
    data.update(overrides)
    return BacktestResult(**data)


def test_insights_good_result():
    periods = [
        PeriodAnalytics("period_1", 100.0, 101.0, 1.0, 0.01, 5),
        PeriodAnalytics("period_2", 101.0, 102.0, 1.0, 0.0099, 5),
    ]

    insights = BacktestInsightsEngine().build_insights(make_result(), periods)

    assert insights.rating == "GOOD"
    assert insights.strengths


def test_insights_no_trades():
    insights = BacktestInsightsEngine().build_insights(
        make_result(trades=0, winning_trades=0, losing_trades=0)
    )

    assert insights.rating == "NO_TRADES"
    assert insights.warnings


def test_insights_weak_result():
    insights = BacktestInsightsEngine().build_insights(
        make_result(net_profit=-1.0, roi=-0.01, profit_factor=0.5)
    )

    assert insights.rating == "WEAK"
