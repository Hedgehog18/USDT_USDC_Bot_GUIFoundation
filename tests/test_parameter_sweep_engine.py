from backtest.historical_data_provider import HistoricalCandle
from backtest.parameter_sweep_engine import ParameterSweepEngine


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


def test_parameter_sweep_runs_all_combinations(test_config):
    results = ParameterSweepEngine(test_config).run(
        candles=make_candles(80),
        target_profits=[0.0001, 0.0002],
        trade_size_percents=[0.05, 0.10],
    )

    assert len(results) == 4
    assert results[0].score >= results[-1].score
