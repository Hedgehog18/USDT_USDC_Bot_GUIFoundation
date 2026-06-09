from pathlib import Path

from backtest.models import BacktestResult
from backtest.parameter_sweep_engine import ParameterSet
from backtest.walk_forward_engine import WalkForwardResult, WalkForwardWindowResult
from backtest.walk_forward_exporter import WalkForwardExporter


def test_walk_forward_exporter(tmp_path: Path):
    result = WalkForwardResult(1, 0.01, 0.6, 5, 1, 70.0)
    backtest_result = BacktestResult(
        symbol="USDCUSDT",
        interval="1m",
        candles=100,
        signals=5,
        trades=5,
        winning_trades=3,
        losing_trades=2,
        win_rate=0.6,
        gross_profit=1.0,
        total_fees=0.2,
        net_profit=0.8,
        roi=0.008,
        final_value=100.8,
        max_drawdown=0.01,
    )
    windows = [
        WalkForwardWindowResult(
            window_index=1,
            train_start=0,
            train_end=80,
            test_start=80,
            test_end=120,
            best_parameters=ParameterSet(0.0002, 0.1),
            train_score=10.0,
            test_result=backtest_result,
            test_score=8.0,
        )
    ]

    path = WalkForwardExporter(str(tmp_path)).export_csv(result, windows)

    assert path.exists()
    assert (tmp_path / "walk_forward_summary.csv").exists()
