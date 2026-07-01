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
                "close_reason",
                "best_price_after_entry",
                "worst_price_after_entry",
                "max_favorable_pnl",
                "max_adverse_pnl",
                "min_distance_to_target",
                "was_target_touched",
                "was_near_target",
                "near_target_threshold",
                "close_gap_to_target",
                "best_possible_pnl",
                "missed_pnl",
                "execution_quality_ratio",
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

    def export_summary_csv(
        self,
        stats: PaperAnalytics,
        strategy_profile: str = "strict_current",
    ) -> Path:
        path = self.reports_dir / "paper_summary_report.csv"

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "total_cycles",
                "closed_cycles",
                "winning_cycles",
                "breakeven_cycles",
                "losing_cycles",
                "win_rate",
                "gross_profit",
                "net_profit",
                "average_net_profit",
                "average_profit",
                "average_loss",
                "average_cycle_pnl",
                "expectancy",
                "profit_factor",
                "timeout_closed",
                "timeout_profit_cycles",
                "timeout_breakeven_cycles",
                "timeout_loss_cycles",
                "timeout_average_pnl",
                "timeout_max_profit",
                "timeout_max_loss",
                "target_closed",
                "target_total_profit",
                "target_average_profit",
                "buy_count",
                "buy_total_pnl",
                "buy_average_pnl",
                "buy_win_rate",
                "sell_count",
                "sell_total_pnl",
                "sell_average_pnl",
                "sell_win_rate",
                "missed_target_count",
                "missed_target_timeout_count",
                "missed_target_then_loss_count",
                "average_missed_target_distance",
                "average_missed_pnl",
                "max_adverse_pnl",
                "average_adverse_pnl",
                "average_favorable_pnl",
                "worst_close_gap_to_target",
                "strategy_profile",
            ])
            writer.writerow([
                stats.total_cycles,
                stats.closed_cycles,
                stats.winning_cycles,
                stats.breakeven_cycles,
                stats.losing_cycles,
                stats.win_rate,
                stats.gross_profit,
                stats.net_profit,
                stats.average_net_profit,
                stats.average_profit,
                stats.average_loss,
                stats.average_cycle_pnl,
                stats.expectancy,
                stats.profit_factor,
                stats.timeout_closed,
                stats.timeout_profit_cycles,
                stats.timeout_breakeven_cycles,
                stats.timeout_loss_cycles,
                stats.timeout_average_pnl,
                stats.timeout_max_profit,
                stats.timeout_max_loss,
                stats.target_closed,
                stats.target_total_profit,
                stats.target_average_profit,
                stats.buy_count,
                stats.buy_total_pnl,
                stats.buy_average_pnl,
                stats.buy_win_rate,
                stats.sell_count,
                stats.sell_total_pnl,
                stats.sell_average_pnl,
                stats.sell_win_rate,
                stats.missed_target_count,
                stats.missed_target_timeout_count,
                stats.missed_target_then_loss_count,
                stats.average_missed_target_distance,
                stats.average_missed_pnl,
                stats.max_adverse_pnl,
                stats.average_adverse_pnl,
                stats.average_favorable_pnl,
                stats.worst_close_gap_to_target,
                strategy_profile,
            ])

        return path
