from backtest.historical_data_provider import HistoricalCandle
from analytics.ml_dataset_coverage_engine import MLDatasetCoverageEngine


def _candles(count: int) -> list[HistoricalCandle]:
    rows = []
    base_time = 1_700_000_000_000
    for index in range(count):
        close = 1.0 + index * 0.000001
        rows.append(
            HistoricalCandle(
                open_time=base_time + index * 60_000,
                open=close - 0.000002,
                high=close + 0.000004,
                low=close - 0.000004,
                close=close,
                volume=100.0,
            )
        )
    return rows


def test_ml_dataset_coverage_explains_zero_candidates(test_config):
    report = MLDatasetCoverageEngine(test_config).build_report(
        candles=_candles(40),
        profile="mean_reversion_v2_small_target",
    )

    assert report.total_rows == 10
    assert report.candidate_rows == 0
    assert report.work_position_min is not None
    assert report.work_position_max is not None
    assert report.work_position_avg is not None
    assert report.micro_trend_distribution
    assert report.all_filters_pass_count == 0
    assert report.recommendation
