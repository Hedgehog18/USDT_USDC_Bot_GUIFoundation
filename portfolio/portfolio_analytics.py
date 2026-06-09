from dataclasses import dataclass

from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class PortfolioStats:
    total_cycles: int
    closed_cycles: int
    active_cycles: int
    winning_cycles: int
    win_rate: float
    realized_profit: float
    average_profit_per_closed_cycle: float
    total_deposits: float
    net_deposits: float
    removed_from_budget: float
    portfolio_value: float
    roi: float


class PortfolioAnalytics:
    """Аналітика портфеля на основі локальної SQLite бази."""

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def calculate_stats(self, current_portfolio_value: float) -> PortfolioStats:
        total_cycles = self.database.count_cycles_total()
        closed_cycles = self.database.count_cycles_by_status("CLOSED")
        active_cycles = self.database.count_active_cycles()
        winning_cycles = self.database.count_winning_cycles()

        realized_profit = self.database.sum_realized_profit()
        total_deposits = self.database.sum_total_deposits()
        removed_from_budget = self.database.sum_removed_from_budget()
        net_deposits = self.database.calculate_net_deposits()

        win_rate = 0.0
        if closed_cycles > 0:
            win_rate = winning_cycles / closed_cycles

        average_profit = 0.0
        if closed_cycles > 0:
            average_profit = realized_profit / closed_cycles

        roi = 0.0
        if net_deposits > 0:
            roi = realized_profit / net_deposits

        return PortfolioStats(
            total_cycles=total_cycles,
            closed_cycles=closed_cycles,
            active_cycles=active_cycles,
            winning_cycles=winning_cycles,
            win_rate=win_rate,
            realized_profit=realized_profit,
            average_profit_per_closed_cycle=average_profit,
            total_deposits=total_deposits,
            net_deposits=net_deposits,
            removed_from_budget=removed_from_budget,
            portfolio_value=current_portfolio_value,
            roi=roi,
        )
