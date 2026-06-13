import csv

import pytest

from analytics.ml_dataset_summary_engine import MLDatasetSummaryEngine


def test_ml_dataset_summary_engine_groups_candidate_hit_rates(tmp_path):
    path = tmp_path / "dataset.csv"
    rows = [
        {
            "timestamp": "2026-06-13T00:01:00+00:00",
            "candidate_direction": "BUY_USDC",
            "label_target_hit": "1",
            "work_position": "12.0",
            "volatility_regime": "NORMAL",
        },
        {
            "timestamp": "2026-06-13T00:02:00+00:00",
            "candidate_direction": "BUY_USDC",
            "label_target_hit": "0",
            "work_position": "18.0",
            "volatility_regime": "NORMAL",
        },
        {
            "timestamp": "2026-06-13T01:01:00+00:00",
            "candidate_direction": "SELL_USDC",
            "label_target_hit": "1",
            "work_position": "82.0",
            "volatility_regime": "LOW",
        },
        {
            "timestamp": "2026-06-13T02:01:00+00:00",
            "candidate_direction": "WAIT",
            "label_target_hit": "1",
            "work_position": "50.0",
            "volatility_regime": "NORMAL",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    report = MLDatasetSummaryEngine().build_report(path)

    assert report.total_rows == 4
    assert report.candidate_rows == 3
    assert report.target_hit_positive_count == 2
    assert report.target_hit_negative_count == 1
    assert report.positive_rate == pytest.approx(2 / 3)
    assert report.direction_distribution == {"BUY_USDC": 2, "SELL_USDC": 1}

    by_direction = {row.name: row for row in report.target_hit_rate_by_direction}
    assert by_direction["BUY_USDC"].positive_rate == pytest.approx(0.5)
    assert by_direction["SELL_USDC"].positive_rate == pytest.approx(1.0)

    by_bucket = {row.name: row for row in report.target_hit_rate_by_work_position_bucket}
    assert by_bucket["10-20"].total == 2
    assert by_bucket["80-90"].total == 1

    by_hour = {row.name: row for row in report.target_hit_rate_by_hour}
    assert by_hour["00:00"].total == 2
    assert by_hour["01:00"].total == 1
