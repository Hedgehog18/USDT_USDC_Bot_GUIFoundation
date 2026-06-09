from pathlib import Path

from backtest.backtest_report_exporter import BacktestReportExporter
from backtest.models import BacktestResult, BacktestTrade


def test_backtest_report_exporter_creates_files(tmp_path: Path):
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
    trades = [
        BacktestTrade(
            index=1,
            action="BUY_USDC",
            entry_price=1.0,
            exit_price=1.001,
            quantity=10.0,
            gross_profit=0.01,
            fees=0.002,
            net_profit=0.008,
        )
    ]

    exporter = BacktestReportExporter(str(tmp_path))
    summary = exporter.export_summary_csv(1, result)
    trades_csv = exporter.export_trades_csv(1, result, trades)

    assert summary.exists()
    assert trades_csv.exists()
    assert "backtest_run_1_summary.csv" in summary.name
    assert "backtest_run_1_trades.csv" in trades_csv.name
