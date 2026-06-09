from pathlib import Path

from backtest.models import BacktestResult
from backtest.parameter_sweep_engine import ParameterSet, ParameterSweepResult
from backtest.parameter_sweep_exporter import ParameterSweepExporter


def test_parameter_sweep_exporter(tmp_path: Path):
    result = BacktestResult(
        symbol="USDCUSDT",
        interval="1m",
        candles=100,
        signals=5,
        trades=2,
        winning_trades=1,
        losing_trades=1,
        win_rate=0.5,
        gross_profit=1.0,
        total_fees=0.2,
        net_profit=0.8,
        roi=0.008,
        final_value=100.8,
        max_drawdown=0.01,
    )
    rows = [
        ParameterSweepResult(
            parameters=ParameterSet(target_profit=0.0002, trade_size_percent=0.1),
            backtest_result=result,
            score=50.0,
        )
    ]

    path = ParameterSweepExporter(str(tmp_path)).export_csv(rows)

    assert path.exists()
    assert path.name == "parameter_sweep.csv"
