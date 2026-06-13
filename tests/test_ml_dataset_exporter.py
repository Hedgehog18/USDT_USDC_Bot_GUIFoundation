import csv

from analytics.ml_dataset_exporter import MLDatasetExporter
from backtest.historical_data_provider import HistoricalCandle


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


def test_ml_dataset_exporter_writes_expected_columns(test_config, tmp_path):
    result = MLDatasetExporter(test_config, output_dir=tmp_path).export(
        candles=_candles(40),
        symbol="USDCUSDT",
        interval="1m",
        profile="mean_reversion_v2_small_target",
    )

    assert result.path.name == "usdcusdt_1m_mean_reversion_v2_small_target.csv"
    assert result.rows_written == 10
    assert result.path.exists()

    with result.path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 10
    first = rows[0]
    assert first["timestamp"]
    assert first["dataset_mode"] == "profile"
    assert first["open"]
    assert first["high"]
    assert first["low"]
    assert first["close"]
    assert first["work_position"]
    assert first["short_position"]
    assert first["long_position"]
    assert first["micro_trend"]
    assert first["market_regime"]
    assert first["volatility_regime"]
    assert first["spread"]
    assert first["candidate_direction"] in {"WAIT", "BUY_USDC", "SELL_USDC"}
    assert first["target_hit_5"] in {"0", "1"}
    assert first["target_hit_10"] in {"0", "1"}
    assert first["target_hit_20"] in {"0", "1"}
    assert first["target_hit_30"] in {"0", "1"}
    assert first["label_target_hit"] in {"0", "1"}


def test_ml_dataset_exporter_no_micro_trend_mode_creates_candidates(test_config, tmp_path):
    result = MLDatasetExporter(test_config, output_dir=tmp_path).export(
        candles=_candles(40),
        symbol="USDCUSDT",
        interval="1m",
        profile="mean_reversion_v2_small_target",
        dataset_mode="no_micro_trend",
    )

    assert result.path.name == "usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv"
    assert result.rows_written == 10
    assert result.candidate_rows > 0

    with result.path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    assert any(row["candidate_direction"] in {"BUY_USDC", "SELL_USDC"} for row in rows)
    assert {row["dataset_mode"] for row in rows} == {"no_micro_trend"}
