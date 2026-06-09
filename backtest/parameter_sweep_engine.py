from dataclasses import dataclass, replace

from backtest.backtest_engine import BacktestEngine
from backtest.historical_data_provider import HistoricalCandle
from backtest.models import BacktestResult
from config.config_manager import BotConfig


@dataclass(frozen=True)
class ParameterSet:
    target_profit: float
    trade_size_percent: float


@dataclass(frozen=True)
class ParameterSweepResult:
    parameters: ParameterSet
    backtest_result: BacktestResult
    score: float


class ParameterSweepEngine:
    """Підбір параметрів через серію backtest-запусків."""

    def __init__(self, base_config: BotConfig) -> None:
        self.base_config = base_config

    def run(
        self,
        candles: list[HistoricalCandle],
        target_profits: list[float],
        trade_size_percents: list[float],
    ) -> list[ParameterSweepResult]:
        results: list[ParameterSweepResult] = []

        for target_profit in target_profits:
            for trade_size_percent in trade_size_percents:
                config = replace(
                    self.base_config,
                    target_profit=target_profit,
                    trade_size_percent=trade_size_percent,
                )
                backtest_result, _trades = BacktestEngine(config).run(candles)

                results.append(
                    ParameterSweepResult(
                        parameters=ParameterSet(
                            target_profit=target_profit,
                            trade_size_percent=trade_size_percent,
                        ),
                        backtest_result=backtest_result,
                        score=self._score(backtest_result),
                    )
                )

        return sorted(results, key=lambda item: item.score, reverse=True)

    @staticmethod
    def _score(result: BacktestResult) -> float:
        if result.trades <= 0:
            return -100.0

        roi_score = result.roi * 1000
        win_score = result.win_rate * 100
        drawdown_penalty = result.max_drawdown * 200
        trade_bonus = min(result.trades, 100) * 0.05

        return roi_score + win_score + trade_bonus - drawdown_penalty
