import csv
from pathlib import Path

from backtest.parameter_sweep_engine import ParameterSweepResult


class ParameterSweepExporter:
    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(self, rows: list[ParameterSweepResult]) -> Path:
        path = self.reports_dir / "parameter_sweep.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "rank",
                "target_profit",
                "trade_size_percent",
                "signals",
                "trades",
                "win_rate",
                "net_profit",
                "roi",
                "max_drawdown",
                "score",
            ])

            for rank, row in enumerate(rows, start=1):
                result = row.backtest_result
                writer.writerow([
                    rank,
                    row.parameters.target_profit,
                    row.parameters.trade_size_percent,
                    result.signals,
                    result.trades,
                    result.win_rate,
                    result.net_profit,
                    result.roi,
                    result.max_drawdown,
                    row.score,
                ])

        return path
