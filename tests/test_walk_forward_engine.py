from backtest.historical_data_provider import HistoricalCandle
from backtest.walk_forward_engine import WalkForwardEngine


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


def test_walk_forward_runs_windows(test_config):
    result, windows = WalkForwardEngine(test_config).run(
        candles=make_candles(160),
        target_profits=[0.0001, 0.0002],
        trade_size_percents=[0.05],
        train_size=80,
        test_size=40,
    )

    assert result.windows == 2
    assert len(windows) == 2
    assert result.total_test_trades >= 0


def test_walk_forward_handles_not_enough_data(test_config):
    result, windows = WalkForwardEngine(test_config).run(
        candles=make_candles(50),
        target_profits=[0.0001],
        trade_size_percents=[0.05],
        train_size=80,
        test_size=40,
    )

    assert result.windows == 0
    assert windows == []
