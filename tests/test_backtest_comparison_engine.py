from backtest.backtest_comparison_engine import BacktestComparisonEngine


class FakeDatabase:
    def load_recent_backtest_runs(self, limit: int = 10):
        return [
            (1, "2026-01-01", "USDCUSDT", "1m", 500, 10, 0.6, 0.5, 0.005, 0.01),
            (2, "2026-01-02", "USDCUSDT", "1m", 500, 20, 0.8, 1.0, 0.010, 0.02),
            (3, "2026-01-03", "USDCUSDT", "1m", 500, 0, 0.0, 0.0, 0.0, 0.0),
        ]


def test_backtest_comparison_ranks_runs():
    engine = BacktestComparisonEngine(FakeDatabase())
    rows = engine.get_ranked_runs()

    assert rows[0].run_id == 2
    assert rows[-1].run_id == 3


def test_backtest_comparison_score_penalizes_no_trades():
    score = BacktestComparisonEngine._score(
        win_rate=1.0,
        roi=1.0,
        max_drawdown=0.0,
        trades=0,
    )

    assert score == -100.0
