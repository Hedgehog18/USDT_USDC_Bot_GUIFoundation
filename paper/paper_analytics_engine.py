from dataclasses import dataclass


@dataclass(frozen=True)
class PaperAnalytics:
    total_cycles: int
    closed_cycles: int
    winning_cycles: int
    losing_cycles: int
    win_rate: float
    gross_profit: float
    net_profit: float
    average_net_profit: float
    profit_factor: float


class PaperAnalyticsEngine:
    def build_from_rows(self, rows: list[tuple]) -> PaperAnalytics:
        closed_rows = [row for row in rows if row[3] == "CLOSED"]
        closed = len(closed_rows)
        winning = sum(1 for row in closed_rows if float(row[10]) > 0)
        losing = sum(1 for row in closed_rows if float(row[10]) <= 0)

        gross_profit = sum(float(row[9]) for row in closed_rows)
        net_profit = sum(float(row[10]) for row in closed_rows)

        positive = sum(float(row[10]) for row in closed_rows if float(row[10]) > 0)
        negative = abs(sum(float(row[10]) for row in closed_rows if float(row[10]) < 0))

        return PaperAnalytics(
            total_cycles=len(rows),
            closed_cycles=closed,
            winning_cycles=winning,
            losing_cycles=losing,
            win_rate=(winning / closed) if closed else 0.0,
            gross_profit=gross_profit,
            net_profit=net_profit,
            average_net_profit=(net_profit / closed) if closed else 0.0,
            profit_factor=(positive / negative) if negative > 0 else (positive if positive > 0 else 0.0),
        )
