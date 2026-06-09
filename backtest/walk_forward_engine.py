from dataclasses import dataclass, replace

from backtest.backtest_engine import BacktestEngine
from backtest.historical_data_provider import HistoricalCandle
from backtest.models import BacktestResult
from backtest.parameter_sweep_engine import ParameterSet, ParameterSweepEngine
from config.config_manager import BotConfig


@dataclass(frozen=True)
class WalkForwardWindowResult:
    window_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    best_parameters: ParameterSet
    train_score: float
    test_result: BacktestResult
    test_score: float


@dataclass(frozen=True)
class WalkForwardResult:
    windows: int
    average_test_roi: float
    average_test_win_rate: float
    total_test_trades: int
    profitable_windows: int
    robustness_score: float


class WalkForwardEngine:
    def __init__(self, base_config: BotConfig) -> None:
        self.base_config = base_config

    def run(
        self,
        candles: list[HistoricalCandle],
        target_profits: list[float],
        trade_size_percents: list[float],
        train_size: int,
        test_size: int,
    ) -> tuple[WalkForwardResult, list[WalkForwardWindowResult]]:
        if train_size <= 0 or test_size <= 0:
            raise ValueError("train_size і test_size мають бути більшими за 0.")

        windows: list[WalkForwardWindowResult] = []
        start = 0
        window_index = 1

        while start + train_size + test_size <= len(candles):
            train_start = start
            train_end = start + train_size
            test_start = train_end
            test_end = test_start + test_size

            train_candles = candles[train_start:train_end]
            test_candles = candles[test_start:test_end]

            sweep = ParameterSweepEngine(self.base_config).run(
                candles=train_candles,
                target_profits=target_profits,
                trade_size_percents=trade_size_percents,
            )

            if not sweep:
                break

            best = sweep[0]
            test_config = replace(
                self.base_config,
                target_profit=best.parameters.target_profit,
                trade_size_percent=best.parameters.trade_size_percent,
            )

            test_result, _ = BacktestEngine(test_config).run(test_candles)
            test_score = ParameterSweepEngine._score(test_result)

            windows.append(
                WalkForwardWindowResult(
                    window_index=window_index,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    best_parameters=best.parameters,
                    train_score=best.score,
                    test_result=test_result,
                    test_score=test_score,
                )
            )

            start += test_size
            window_index += 1

        return self._summary(windows), windows

    @staticmethod
    def _summary(windows: list[WalkForwardWindowResult]) -> WalkForwardResult:
        if not windows:
            return WalkForwardResult(
                windows=0,
                average_test_roi=0.0,
                average_test_win_rate=0.0,
                total_test_trades=0,
                profitable_windows=0,
                robustness_score=0.0,
            )

        avg_roi = sum(w.test_result.roi for w in windows) / len(windows)
        avg_win = sum(w.test_result.win_rate for w in windows) / len(windows)
        total_trades = sum(w.test_result.trades for w in windows)
        profitable = sum(1 for w in windows if w.test_result.net_profit > 0)
        profitable_ratio = profitable / len(windows)

        robustness = (
            avg_roi * 1000
            + avg_win * 100
            + profitable_ratio * 100
            + min(total_trades, 100) * 0.05
        )

        return WalkForwardResult(
            windows=len(windows),
            average_test_roi=avg_roi,
            average_test_win_rate=avg_win,
            total_test_trades=total_trades,
            profitable_windows=profitable,
            robustness_score=robustness,
        )
