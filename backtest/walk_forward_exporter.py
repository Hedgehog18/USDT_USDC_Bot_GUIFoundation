import csv
from pathlib import Path

from backtest.walk_forward_engine import WalkForwardResult, WalkForwardWindowResult


class WalkForwardExporter:
    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(self, result: WalkForwardResult, windows: list[WalkForwardWindowResult]) -> Path:
        path = self.reports_dir / "walk_forward.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "window_index",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                "target_profit",
                "trade_size_percent",
                "train_score",
                "test_score",
                "test_trades",
                "test_win_rate",
                "test_net_profit",
                "test_roi",
                "test_max_drawdown",
            ])

            for item in windows:
                writer.writerow([
                    item.window_index,
                    item.train_start,
                    item.train_end,
                    item.test_start,
                    item.test_end,
                    item.best_parameters.target_profit,
                    item.best_parameters.trade_size_percent,
                    item.train_score,
                    item.test_score,
                    item.test_result.trades,
                    item.test_result.win_rate,
                    item.test_result.net_profit,
                    item.test_result.roi,
                    item.test_result.max_drawdown,
                ])

        summary = self.reports_dir / "walk_forward_summary.csv"
        with summary.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "windows",
                "average_test_roi",
                "average_test_win_rate",
                "total_test_trades",
                "profitable_windows",
                "robustness_score",
            ])
            writer.writerow([
                result.windows,
                result.average_test_roi,
                result.average_test_win_rate,
                result.total_test_trades,
                result.profitable_windows,
                result.robustness_score,
            ])

        return path
