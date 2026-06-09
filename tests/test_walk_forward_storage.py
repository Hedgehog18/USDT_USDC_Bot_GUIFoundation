from pathlib import Path

from backtest.models import BacktestResult
from backtest.parameter_sweep_engine import ParameterSet
from backtest.walk_forward_engine import WalkForwardResult, WalkForwardWindowResult
from storage.database_manager import DatabaseManager


def test_database_saves_walk_forward_result(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    result = WalkForwardResult(
        windows=1,
        average_test_roi=0.01,
        average_test_win_rate=0.6,
        total_test_trades=5,
        profitable_windows=1,
        robustness_score=70.0,
    )
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

    run_id = database.save_walk_forward_result(result, windows)

    assert run_id > 0
    assert database.count_rows("walk_forward_runs") == 1
    assert database.count_rows("walk_forward_windows") == 1
