from pathlib import Path

from backtest.models import BacktestResult, BacktestTrade
from storage.database_manager import DatabaseManager


def test_database_saves_backtest_result(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    result = BacktestResult(
        symbol="USDCUSDT",
        interval="1m",
        candles=100,
        signals=5,
        trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate=1.0,
        gross_profit=1.0,
        total_fees=0.2,
        net_profit=0.8,
        roi=0.008,
        final_value=100.8,
        max_drawdown=0.01,
    )
    trades = [
        BacktestTrade(
            index=10,
            action="BUY_USDC",
            entry_price=1.0,
            exit_price=1.001,
            quantity=10.0,
            gross_profit=0.01,
            fees=0.002,
            net_profit=0.008,
        )
    ]

    run_id = database.save_backtest_result(result, trades)

    assert run_id > 0
    assert database.count_rows("backtest_runs") == 1
    assert database.count_rows("backtest_trades") == 1
    assert database.load_backtest_trades(run_id) == [
        (10, "BUY_USDC", 1.0, 1.001, 10.0, 0.01, 0.002, 0.008)
    ]
