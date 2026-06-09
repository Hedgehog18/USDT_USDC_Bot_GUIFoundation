from dataclasses import dataclass
from statistics import mean, pstdev

from backtest.models import BacktestTrade


@dataclass(frozen=True)
class BacktestAdvancedMetrics:
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    expectancy: float
    returns: list[float]


class BacktestMetricsEngine:
    def calculate(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[float],
    ) -> BacktestAdvancedMetrics:
        returns = self._calculate_returns(equity_curve)

        return BacktestAdvancedMetrics(
            sharpe_ratio=self._sharpe_ratio(returns),
            sortino_ratio=self._sortino_ratio(returns),
            profit_factor=self._profit_factor(trades),
            expectancy=self._expectancy(trades),
            returns=returns,
        )

    @staticmethod
    def _calculate_returns(equity_curve: list[float]) -> list[float]:
        if len(equity_curve) < 2:
            return []

        result: list[float] = []
        for previous, current in zip(equity_curve, equity_curve[1:]):
            if previous > 0:
                result.append((current - previous) / previous)

        return result

    @staticmethod
    def _sharpe_ratio(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0

        std = pstdev(returns)
        if std == 0:
            return 0.0

        return mean(returns) / std

    @staticmethod
    def _sortino_ratio(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0

        downside = [item for item in returns if item < 0]
        if len(downside) < 2:
            return 0.0

        downside_std = pstdev(downside)
        if downside_std == 0:
            return 0.0

        return mean(returns) / downside_std

    @staticmethod
    def _profit_factor(trades: list[BacktestTrade]) -> float:
        profit = sum(trade.net_profit for trade in trades if trade.net_profit > 0)
        loss = abs(sum(trade.net_profit for trade in trades if trade.net_profit < 0))

        if loss == 0:
            return profit if profit > 0 else 0.0

        return profit / loss

    @staticmethod
    def _expectancy(trades: list[BacktestTrade]) -> float:
        if not trades:
            return 0.0

        return sum(trade.net_profit for trade in trades) / len(trades)
