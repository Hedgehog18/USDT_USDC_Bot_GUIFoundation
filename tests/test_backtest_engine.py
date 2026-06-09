from backtest.backtest_engine import BacktestEngine
from backtest.historical_data_provider import HistoricalCandle


def make_candles(count: int):
    candles = []
    price = 1.0
    for index in range(count):
        price += 0.00001 if index % 2 == 0 else -0.000005
        candles.append(
            HistoricalCandle(
                open_time=index,
                open=price,
                high=price * 1.001,
                low=price * 0.999,
                close=price,
                volume=100.0,
            )
        )
    return candles


def test_backtest_engine_returns_result(test_config):
    result, trades = BacktestEngine(test_config).run(make_candles(80))

    assert result.candles == 80
    assert result.trades >= 0
    assert result.final_value > 0
    assert result.max_drawdown >= 0


def test_backtest_engine_handles_small_dataset(test_config):
    result, trades = BacktestEngine(test_config).run(make_candles(10))

    assert result.candles == 10
    assert result.trades == 0
    assert trades == []
