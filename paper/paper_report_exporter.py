import csv
from pathlib import Path

from paper.paper_analytics_engine import PaperAnalytics


class PaperReportExporter:
    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def export_cycles_csv(self, rows: list[tuple]) -> Path:
        path = self.reports_dir / "paper_cycles_report.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "cycle_id",
                "direction",
                "status",
                "open_price",
                "close_price",
                "quantity",
                "open_fee",
                "close_fee",
                "gross_profit",
                "net_profit",
            ])
            writer.writerows(rows)

        return path

    def export_safety_csv(self, rows: list[tuple]) -> Path:
        path = self.reports_dir / "paper_safety_report.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "level",
                "allowed",
                "reason",
                "portfolio_value",
            ])
            writer.writerows(rows)

        return path

    def export_summary_csv(self, stats: PaperAnalytics) -> Path:
        path = self.reports_dir / "paper_summary_report.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "total_cycles",
                "closed_cycles",
                "winning_cycles",
                "losing_cycles",
                "win_rate",
                "gross_profit",
                "net_profit",
                "average_net_profit",
                "profit_factor",
            ])
            writer.writerow([
                stats.total_cycles,
                stats.closed_cycles,
                stats.winning_cycles,
                stats.losing_cycles,
                stats.win_rate,
                stats.gross_profit,
                stats.net_profit,
                stats.average_net_profit,
                stats.profit_factor,
            ])

        return path
