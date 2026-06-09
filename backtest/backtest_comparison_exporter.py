import csv
from pathlib import Path

from backtest.backtest_comparison_engine import BacktestRunSummary


class BacktestComparisonExporter:
    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(self, rows: list[BacktestRunSummary]) -> Path:
        path = self.reports_dir / "backtest_comparison.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "rank",
                "run_id",
                "timestamp",
                "symbol",
                "interval",
                "candles",
                "trades",
                "win_rate",
                "net_profit",
                "roi",
                "max_drawdown",
                "score",
            ])

            for rank, row in enumerate(rows, start=1):
                writer.writerow([
                    rank,
                    row.run_id,
                    row.timestamp,
                    row.symbol,
                    row.interval,
                    row.candles,
                    row.trades,
                    row.win_rate,
                    row.net_profit,
                    row.roi,
                    row.max_drawdown,
                    row.score,
                ])

        return path
