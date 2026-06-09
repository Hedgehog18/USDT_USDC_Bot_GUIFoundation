import csv
from pathlib import Path

from backtest.models import BacktestResult, BacktestTrade


class BacktestReportExporter:
    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def export_trades_csv(
        self,
        run_id: int,
        result: BacktestResult,
        trades: list[BacktestTrade],
    ) -> Path:
        path = self.reports_dir / f"backtest_run_{run_id}_trades.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "run_id",
                "symbol",
                "interval",
                "trade_index",
                "action",
                "entry_price",
                "exit_price",
                "quantity",
                "gross_profit",
                "fees",
                "net_profit",
            ])

            for trade in trades:
                writer.writerow([
                    run_id,
                    result.symbol,
                    result.interval,
                    trade.index,
                    trade.action,
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    trade.gross_profit,
                    trade.fees,
                    trade.net_profit,
                ])

        return path

    def export_summary_csv(self, run_id: int, result: BacktestResult) -> Path:
        path = self.reports_dir / f"backtest_run_{run_id}_summary.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "run_id",
                "symbol",
                "interval",
                "candles",
                "signals",
                "trades",
                "winning_trades",
                "losing_trades",
                "win_rate",
                "gross_profit",
                "total_fees",
                "net_profit",
                "roi",
                "final_value",
                "max_drawdown",
                "sharpe_ratio",
                "sortino_ratio",
                "profit_factor",
                "expectancy",
            ])
            writer.writerow([
                run_id,
                result.symbol,
                result.interval,
                result.candles,
                result.signals,
                result.trades,
                result.winning_trades,
                result.losing_trades,
                result.win_rate,
                result.gross_profit,
                result.total_fees,
                result.net_profit,
                result.roi,
                result.final_value,
                result.max_drawdown,
                result.sharpe_ratio,
                result.sortino_ratio,
                result.profit_factor,
                result.expectancy,
            ])

        return path

    def export_equity_csv(self, run_id: int, equity_points: list) -> Path:
        path = self.reports_dir / f"backtest_run_{run_id}_equity.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["run_id", "point_index", "value"])
            for point in equity_points:
                writer.writerow([run_id, point.index, point.value])

        return path

    def export_period_analytics_csv(self, run_id: int, periods: list) -> Path:
        path = self.reports_dir / f"backtest_run_{run_id}_periods.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "run_id",
                "period",
                "start_value",
                "end_value",
                "profit",
                "roi",
                "trades",
            ])
            for period in periods:
                writer.writerow([
                    run_id,
                    period.period,
                    period.start_value,
                    period.end_value,
                    period.profit,
                    period.roi,
                    period.trades,
                ])

        return path
