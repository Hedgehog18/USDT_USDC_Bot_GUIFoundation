from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


WORK_POSITION_BUCKETS = (
    (0.0, 10.0, "0-10"),
    (10.0, 20.0, "10-20"),
    (20.0, 30.0, "20-30"),
    (30.0, 40.0, "30-40"),
    (40.0, 60.0, "40-60"),
    (60.0, 70.0, "60-70"),
    (70.0, 80.0, "70-80"),
    (80.0, 90.0, "80-90"),
    (90.0, 100.0, "90-100"),
)


@dataclass(frozen=True)
class MLDatasetGroupSummary:
    name: str
    total: int
    positives: int
    positive_rate: float


@dataclass(frozen=True)
class MLDatasetSummaryReport:
    file_path: Path
    total_rows: int
    candidate_rows: int
    target_hit_positive_count: int
    target_hit_negative_count: int
    positive_rate: float
    direction_distribution: dict[str, int]
    target_hit_rate_by_direction: list[MLDatasetGroupSummary]
    target_hit_rate_by_work_position_bucket: list[MLDatasetGroupSummary]
    target_hit_rate_by_volatility_regime: list[MLDatasetGroupSummary]
    target_hit_rate_by_hour: list[MLDatasetGroupSummary]


class MLDatasetSummaryEngine:
    def build_report(self, file_path: str | Path) -> MLDatasetSummaryReport:
        path = Path(file_path)
        rows = self._read_rows(path)
        candidate_rows = [row for row in rows if row.get("candidate_direction") in {"BUY_USDC", "SELL_USDC"}]
        positives = sum(1 for row in candidate_rows if self._is_positive(row))
        negatives = len(candidate_rows) - positives

        return MLDatasetSummaryReport(
            file_path=path,
            total_rows=len(rows),
            candidate_rows=len(candidate_rows),
            target_hit_positive_count=positives,
            target_hit_negative_count=negatives,
            positive_rate=self._rate(positives, len(candidate_rows)),
            direction_distribution=dict(sorted(Counter(row["candidate_direction"] for row in candidate_rows).items())),
            target_hit_rate_by_direction=self._group_summary(candidate_rows, lambda row: row["candidate_direction"]),
            target_hit_rate_by_work_position_bucket=self._group_summary(
                candidate_rows,
                lambda row: self._work_position_bucket(row.get("work_position", "")),
            ),
            target_hit_rate_by_volatility_regime=self._group_summary(
                candidate_rows,
                lambda row: row.get("volatility_regime") or "UNKNOWN",
            ),
            target_hit_rate_by_hour=self._group_summary(
                candidate_rows,
                lambda row: self._hour_bucket(row.get("timestamp", "")),
            ),
        )

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    @staticmethod
    def _is_positive(row: dict[str, str]) -> bool:
        return str(row.get("label_target_hit", "0")).strip() == "1"

    def _group_summary(self, rows: list[dict[str, str]], key_func) -> list[MLDatasetGroupSummary]:
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            groups[key_func(row)].append(row)
        summaries = []
        for name in sorted(groups):
            items = groups[name]
            positives = sum(1 for row in items if self._is_positive(row))
            summaries.append(
                MLDatasetGroupSummary(
                    name=name,
                    total=len(items),
                    positives=positives,
                    positive_rate=self._rate(positives, len(items)),
                )
            )
        return summaries

    @staticmethod
    def _work_position_bucket(raw_value: str) -> str:
        try:
            value = float(raw_value)
        except ValueError:
            return "UNKNOWN"
        for low, high, label in WORK_POSITION_BUCKETS:
            if low <= value < high:
                return label
        if value == 100.0:
            return "90-100"
        return "UNKNOWN"

    @staticmethod
    def _hour_bucket(raw_timestamp: str) -> str:
        try:
            parsed = datetime.fromisoformat(raw_timestamp)
        except ValueError:
            return "UNKNOWN"
        return f"{parsed.hour:02d}:00"

    @staticmethod
    def _rate(part: int, total: int) -> float:
        return part / total if total else 0.0
