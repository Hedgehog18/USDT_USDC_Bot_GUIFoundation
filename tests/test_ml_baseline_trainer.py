from __future__ import annotations

import csv
from pathlib import Path

from analytics.ml_baseline_trainer import MLBaselineTrainer


def test_ml_baseline_trainer_writes_offline_report(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    rows = [
        ("2026-06-10T00:00:00", "BUY_USDC", "1", "20", "22", "25", "0.00001", "LOW", "0.1"),
        ("2026-06-10T01:00:00", "SELL_USDC", "0", "80", "78", "75", "0.00002", "LOW", "0.2"),
        ("2026-06-10T02:00:00", "BUY_USDC", "1", "21", "23", "26", "0.00001", "NORMAL", "0.3"),
        ("2026-06-10T03:00:00", "SELL_USDC", "0", "81", "79", "76", "0.00002", "NORMAL", "0.4"),
        ("2026-06-10T04:00:00", "BUY_USDC", "1", "22", "24", "27", "0.00001", "LOW", "0.5"),
        ("2026-06-10T05:00:00", "SELL_USDC", "0", "82", "80", "77", "0.00002", "LOW", "0.6"),
        ("2026-06-10T06:00:00", "BUY_USDC", "1", "23", "25", "28", "0.00001", "NORMAL", "0.7"),
        ("2026-06-10T07:00:00", "SELL_USDC", "0", "83", "81", "78", "0.00002", "NORMAL", "0.8"),
        ("2026-06-10T08:00:00", "BUY_USDC", "1", "24", "26", "29", "0.00001", "LOW", "0.9"),
        ("2026-06-10T09:00:00", "SELL_USDC", "0", "84", "82", "79", "0.00002", "LOW", "1.0"),
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([
            "timestamp",
            "candidate_direction",
            "label_target_hit",
            "work_position",
            "short_position",
            "long_position",
            "spread",
            "volatility_regime",
            "return_1",
            "return_3",
            "return_5",
            "rolling_high_low_range_5",
            "rolling_high_low_range_10",
            "distance_to_work_center",
            "distance_to_short_center",
            "distance_to_long_center",
            "candle_body",
            "candle_range",
            "upper_wick",
            "lower_wick",
        ])
        for row in rows:
            writer.writerow([*row, *([row[-1]] * 11)])

    output_path = tmp_path / "ml_baseline_report.txt"
    report = MLBaselineTrainer(output_path=output_path).train(csv_path)

    assert report.train_rows == 7
    assert report.test_rows == 3
    assert report.precision is not None
    assert report.recall is not None
    assert report.f1 is not None
    assert report.confusion_matrix
    assert report.top_feature_importances
    assert MLBaselineTrainer._features({"return_1": "0.1"})["return_1"] == 0.1
    assert output_path.exists()
    assert "ML Baseline Training Report" in output_path.read_text(encoding="utf-8")
