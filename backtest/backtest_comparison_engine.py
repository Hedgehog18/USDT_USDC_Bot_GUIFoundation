from dataclasses import dataclass

from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class BacktestRunSummary:
    run_id: int
    timestamp: str
    symbol: str
    interval: str
    candles: int
    trades: int
    win_rate: float
    net_profit: float
    roi: float
    max_drawdown: float
    score: float


class BacktestComparisonEngine:
    """Порівняння backtest-запусків.

    MVP-score:
    - ROI має найбільшу вагу;
    - win rate допоміжний;
    - max drawdown штрафує результат.
    """

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def get_ranked_runs(self, limit: int = 20) -> list[BacktestRunSummary]:
        rows = self.database.load_recent_backtest_runs(limit=limit)

        summaries = [
            BacktestRunSummary(
                run_id=int(row[0]),
                timestamp=str(row[1]),
                symbol=str(row[2]),
                interval=str(row[3]),
                candles=int(row[4]),
                trades=int(row[5]),
                win_rate=float(row[6]),
                net_profit=float(row[7]),
                roi=float(row[8]),
                max_drawdown=float(row[9]),
                score=self._score(
                    win_rate=float(row[6]),
                    roi=float(row[8]),
                    max_drawdown=float(row[9]),
                    trades=int(row[5]),
                ),
            )
            for row in rows
        ]

        return sorted(summaries, key=lambda item: item.score, reverse=True)

    @staticmethod
    def _score(win_rate: float, roi: float, max_drawdown: float, trades: int) -> float:
        if trades <= 0:
            return -100.0

        roi_score = roi * 1000
        win_score = win_rate * 100
        drawdown_penalty = max_drawdown * 200
        trade_bonus = min(trades, 100) * 0.05

        return roi_score + win_score + trade_bonus - drawdown_penalty
