from pathlib import Path

from backtest.models import EquityPoint, PeriodAnalytics
from storage.database_manager import DatabaseManager


def test_database_saves_equity_and_periods(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    with database.connect() as conn:
        cursor = conn.execute(
            '''
            INSERT INTO backtest_runs (
                timestamp, symbol, interval, candles, signals, trades,
                winning_trades, losing_trades, win_rate, gross_profit,
                total_fees, net_profit, roi, final_value, max_drawdown
            ) VALUES (
                'now', 'USDCUSDT', '1m', 10, 0, 0,
                0, 0, 0, 0,
                0, 0, 0, 100, 0
            )
            '''
        )
        run_id = int(cursor.lastrowid)
        conn.commit()

    database.save_backtest_equity_points(
        run_id,
        [EquityPoint(index=0, value=100.0), EquityPoint(index=1, value=101.0)],
    )
    database.save_backtest_period_analytics(
        run_id,
        [PeriodAnalytics("period_1", 100.0, 101.0, 1.0, 0.01, 1)],
    )

    assert database.count_rows("backtest_equity_points") == 2
    assert database.count_rows("backtest_period_analytics") == 1

    assert database.load_latest_backtest_run()[0] == run_id
    assert database.load_backtest_equity_points(run_id) == [(0, 100.0), (1, 101.0)]
