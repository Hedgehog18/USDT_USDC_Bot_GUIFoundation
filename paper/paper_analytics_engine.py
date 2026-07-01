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
    breakeven_cycles: int = 0
    average_profit: float = 0.0
    average_loss: float = 0.0
    average_cycle_pnl: float = 0.0
    expectancy: float = 0.0
    timeout_closed: int = 0
    timeout_profit_cycles: int = 0
    timeout_breakeven_cycles: int = 0
    timeout_loss_cycles: int = 0
    timeout_average_pnl: float = 0.0
    timeout_max_profit: float = 0.0
    timeout_max_loss: float = 0.0
    target_closed: int = 0
    target_total_profit: float = 0.0
    target_average_profit: float = 0.0
    buy_count: int = 0
    buy_total_pnl: float = 0.0
    buy_average_pnl: float = 0.0
    buy_win_rate: float = 0.0
    sell_count: int = 0
    sell_total_pnl: float = 0.0
    sell_average_pnl: float = 0.0
    sell_win_rate: float = 0.0
    missed_target_count: int = 0
    missed_target_timeout_count: int = 0
    missed_target_then_loss_count: int = 0
    average_missed_target_distance: float = 0.0
    average_missed_pnl: float = 0.0
    max_adverse_pnl: float = 0.0
    average_adverse_pnl: float = 0.0
    average_favorable_pnl: float = 0.0
    worst_close_gap_to_target: float = 0.0


class PaperAnalyticsEngine:
    def build_from_rows(self, rows: list[tuple]) -> PaperAnalytics:
        closed_rows = [row for row in rows if row[3] in {"CLOSED", "CLOSED_MANUAL"}]
        closed = len(closed_rows)
        winning = sum(1 for row in closed_rows if float(row[10]) > 0)
        breakeven = sum(1 for row in closed_rows if float(row[10]) == 0)
        losing = sum(1 for row in closed_rows if float(row[10]) < 0)

        gross_profit = sum(float(row[9]) for row in closed_rows)
        net_profit = sum(float(row[10]) for row in closed_rows)

        positive_values = [float(row[10]) for row in closed_rows if float(row[10]) > 0]
        negative_values = [float(row[10]) for row in closed_rows if float(row[10]) < 0]
        positive = sum(positive_values)
        negative = abs(sum(negative_values))
        average_profit = (positive / len(positive_values)) if positive_values else 0.0
        average_loss = (sum(negative_values) / len(negative_values)) if negative_values else 0.0

        timeout_rows = [row for row in closed_rows if self._is_timeout_reason(self._close_reason(row))]
        timeout_pnls = [float(row[10]) for row in timeout_rows]
        timeout_profit_values = [value for value in timeout_pnls if value > 0]
        timeout_loss_values = [value for value in timeout_pnls if value < 0]

        target_rows = [row for row in closed_rows if self._close_reason(row) == "target"]
        target_pnls = [float(row[10]) for row in target_rows]

        buy_rows = [row for row in closed_rows if row[2] == "BUY_USDC"]
        sell_rows = [row for row in closed_rows if row[2] == "SELL_USDC"]
        missed_target_rows = [
            row for row in closed_rows
            if self._optional_bool(row, 18) and self._close_reason(row) != "target"
        ]
        missed_target_timeout_rows = [
            row for row in missed_target_rows
            if self._is_timeout_reason(self._close_reason(row))
        ]
        missed_target_then_loss_rows = [
            row for row in missed_target_rows
            if float(row[10]) < 0
        ]
        missed_distances = [self._optional_float(row, 16) for row in missed_target_rows if self._optional_float(row, 16) is not None]
        missed_pnls = [self._optional_float(row, 22) or 0.0 for row in closed_rows]
        adverse_values = [self._optional_float(row, 15) or 0.0 for row in closed_rows]
        favorable_values = [self._optional_float(row, 14) or 0.0 for row in closed_rows]
        close_gaps = [self._optional_float(row, 20) for row in closed_rows if self._optional_float(row, 20) is not None]

        return PaperAnalytics(
            total_cycles=len(rows),
            closed_cycles=closed,
            winning_cycles=winning,
            breakeven_cycles=breakeven,
            losing_cycles=losing,
            win_rate=(winning / closed) if closed else 0.0,
            gross_profit=gross_profit,
            net_profit=net_profit,
            average_net_profit=(net_profit / closed) if closed else 0.0,
            average_profit=average_profit,
            average_loss=average_loss,
            average_cycle_pnl=(net_profit / closed) if closed else 0.0,
            expectancy=self._expectancy(closed, winning, losing, average_profit, average_loss),
            profit_factor=(positive / negative) if negative > 0 else (positive if positive > 0 else 0.0),
            timeout_closed=len(timeout_rows),
            timeout_profit_cycles=len(timeout_profit_values),
            timeout_breakeven_cycles=sum(1 for value in timeout_pnls if value == 0),
            timeout_loss_cycles=len(timeout_loss_values),
            timeout_average_pnl=(sum(timeout_pnls) / len(timeout_pnls)) if timeout_pnls else 0.0,
            timeout_max_profit=max(timeout_profit_values) if timeout_profit_values else 0.0,
            timeout_max_loss=min(timeout_loss_values) if timeout_loss_values else 0.0,
            target_closed=len(target_rows),
            target_total_profit=sum(target_pnls),
            target_average_profit=(sum(target_pnls) / len(target_pnls)) if target_pnls else 0.0,
            buy_count=len(buy_rows),
            buy_total_pnl=sum(float(row[10]) for row in buy_rows),
            buy_average_pnl=self._average_pnl(buy_rows),
            buy_win_rate=self._win_rate(buy_rows),
            sell_count=len(sell_rows),
            sell_total_pnl=sum(float(row[10]) for row in sell_rows),
            sell_average_pnl=self._average_pnl(sell_rows),
            sell_win_rate=self._win_rate(sell_rows),
            missed_target_count=len(missed_target_rows),
            missed_target_timeout_count=len(missed_target_timeout_rows),
            missed_target_then_loss_count=len(missed_target_then_loss_rows),
            average_missed_target_distance=(sum(missed_distances) / len(missed_distances)) if missed_distances else 0.0,
            average_missed_pnl=(sum(missed_pnls) / len(missed_pnls)) if missed_pnls else 0.0,
            max_adverse_pnl=min(adverse_values) if adverse_values else 0.0,
            average_adverse_pnl=(sum(adverse_values) / len(adverse_values)) if adverse_values else 0.0,
            average_favorable_pnl=(sum(favorable_values) / len(favorable_values)) if favorable_values else 0.0,
            worst_close_gap_to_target=max(close_gaps) if close_gaps else 0.0,
        )

    @staticmethod
    def _close_reason(row: tuple) -> str:
        return str(row[11]) if len(row) > 11 and row[11] is not None else ""

    @staticmethod
    def _is_timeout_reason(reason: str) -> bool:
        clean_reason = reason.lower()
        return clean_reason.startswith("max_holding_") or "timeout" in clean_reason

    @staticmethod
    def _average_pnl(rows: list[tuple]) -> float:
        return (sum(float(row[10]) for row in rows) / len(rows)) if rows else 0.0

    @staticmethod
    def _win_rate(rows: list[tuple]) -> float:
        return (sum(1 for row in rows if float(row[10]) > 0) / len(rows)) if rows else 0.0

    @staticmethod
    def _expectancy(
        closed: int,
        winning: int,
        losing: int,
        average_profit: float,
        average_loss: float,
    ) -> float:
        if closed == 0:
            return 0.0
        win_rate = winning / closed
        loss_rate = losing / closed
        return (win_rate * average_profit) + (loss_rate * average_loss)

    @staticmethod
    def _optional_float(row: tuple, index: int) -> float | None:
        if len(row) <= index or row[index] is None:
            return None
        return float(row[index])

    @staticmethod
    def _optional_bool(row: tuple, index: int) -> bool:
        if len(row) <= index or row[index] is None:
            return False
        return bool(row[index])
