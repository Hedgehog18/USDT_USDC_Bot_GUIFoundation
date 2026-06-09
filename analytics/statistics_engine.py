from dataclasses import dataclass

from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class SignalStats:
    total_signals: int
    buy_signals: int
    sell_signals: int
    wait_signals: int
    safe_wait_signals: int
    allowed_signals: int
    blocked_signals: int
    average_cycle_prediction_score: float


@dataclass(frozen=True)
class CycleStats:
    total_cycles: int
    closed_cycles: int
    active_cycles: int
    winning_cycles: int
    win_rate: float
    realized_profit: float
    average_profit: float
    average_duration_seconds: float


@dataclass(frozen=True)
class StatisticsSummary:
    cycle_stats: CycleStats
    signal_stats: SignalStats


class StatisticsEngine:
    """Агрегована статистика по циклах і сигналах.

    На цьому етапі працює з локальною SQLite базою.
    Пізніше сюди можна додати daily/weekly/monthly aggregates.
    """

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self) -> StatisticsSummary:
        return StatisticsSummary(
            cycle_stats=self.build_cycle_stats(),
            signal_stats=self.build_signal_stats(),
        )

    def build_cycle_stats(self) -> CycleStats:
        total_cycles = self.database.count_cycles_total()
        closed_cycles = self.database.count_cycles_by_status("CLOSED")
        active_cycles = self.database.count_active_cycles()
        winning_cycles = self.database.count_winning_cycles()
        realized_profit = self.database.sum_realized_profit()
        average_duration = self.database.average_closed_cycle_duration()

        win_rate = 0.0
        if closed_cycles > 0:
            win_rate = winning_cycles / closed_cycles

        average_profit = 0.0
        if closed_cycles > 0:
            average_profit = realized_profit / closed_cycles

        return CycleStats(
            total_cycles=total_cycles,
            closed_cycles=closed_cycles,
            active_cycles=active_cycles,
            winning_cycles=winning_cycles,
            win_rate=win_rate,
            realized_profit=realized_profit,
            average_profit=average_profit,
            average_duration_seconds=average_duration,
        )

    def build_signal_stats(self) -> SignalStats:
        total_signals = self.database.count_trade_signals_total()
        buy_signals = self.database.count_trade_signals_by_action("BUY_USDC")
        sell_signals = self.database.count_trade_signals_by_action("SELL_USDC")
        wait_signals = self.database.count_trade_signals_by_action("WAIT")
        safe_wait_signals = self.database.count_trade_signals_by_action("SAFE_WAIT")
        allowed_signals = self.database.count_allowed_trade_signals()
        blocked_signals = max(0, total_signals - allowed_signals)
        average_score = self.database.average_cycle_prediction_score()

        return SignalStats(
            total_signals=total_signals,
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            wait_signals=wait_signals,
            safe_wait_signals=safe_wait_signals,
            allowed_signals=allowed_signals,
            blocked_signals=blocked_signals,
            average_cycle_prediction_score=average_score,
        )
