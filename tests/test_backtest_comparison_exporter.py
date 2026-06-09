from pathlib import Path

from backtest.backtest_comparison_engine import BacktestRunSummary
from backtest.backtest_comparison_exporter import BacktestComparisonExporter


def test_backtest_comparison_exporter(tmp_path: Path):
    rows = [
        BacktestRunSummary(
            run_id=1,
            timestamp="2026-01-01",
            symbol="USDCUSDT",
            interval="1m",
            candles=500,
            trades=10,
            win_rate=0.6,
            net_profit=0.5,
            roi=0.005,
            max_drawdown=0.01,
            score=63.0,
        )
    ]

    path = BacktestComparisonExporter(str(tmp_path)).export_csv(rows)

    assert path.exists()
    assert "backtest_comparison.csv" in path.name
