from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HighFrequencyDatasetSummary:
    total_snapshots: int
    potential_micro_entries: int
    potential_micro_entry_rate: float
    by_hour: list[tuple[str, int]]
    by_session: list[tuple[str, int]]
    blockers: list[tuple[str, int]]
    spread_distribution: list[tuple[str, int]]
    micro_trend_distribution: list[tuple[str, int]]
    work_position_distribution: list[tuple[str, int]]


class HighFrequencyDatasetSummaryEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self) -> HighFrequencyDatasetSummary:
        rows = self._load_rows()
        total = len(rows)
        potential = sum(1 for row in rows if row["would_open_cycle"])
        return HighFrequencyDatasetSummary(
            total_snapshots=total,
            potential_micro_entries=potential,
            potential_micro_entry_rate=potential / total if total else 0.0,
            by_hour=self._counter(row["hour"] for row in rows),
            by_session=self._counter(row["session"] for row in rows),
            blockers=self._counter(row["reason_if_not"] or "would_open_cycle" for row in rows),
            spread_distribution=self._counter(self._spread_bucket(row["spread"]) for row in rows),
            micro_trend_distribution=self._counter(row["micro_trend"] for row in rows),
            work_position_distribution=self._counter(self._work_position_bucket(row["work_position"]) for row in rows),
        )

    def _load_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    spread,
                    work_position,
                    micro_trend,
                    session,
                    would_open_cycle,
                    reason_if_not
                FROM market_snapshots_hf
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        for timestamp, spread, work_position, micro_trend, session, would_open_cycle, reason_if_not in rows:
            parsed = self._parse_timestamp(timestamp)
            result.append({
                "hour": f"{parsed.hour:02d}:00" if parsed else "UNKNOWN",
                "spread": float(spread or 0.0),
                "work_position": float(work_position or 0.0),
                "micro_trend": clean_display_text(micro_trend or "UNKNOWN"),
                "session": clean_display_text(session or "UNKNOWN"),
                "would_open_cycle": bool(would_open_cycle),
                "reason_if_not": clean_display_text(reason_if_not or ""),
            })
        return result

    @staticmethod
    def _counter(values) -> list[tuple[str, int]]:
        counter = Counter(values)
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))

    @staticmethod
    def _spread_bucket(spread: float) -> str:
        if spread <= 0.00001:
            return "<=0.00001"
        if spread <= 0.00002:
            return "<=0.00002"
        if spread <= 0.00005:
            return "<=0.00005"
        return ">0.00005"

    @staticmethod
    def _work_position_bucket(position: float) -> str:
        buckets = (
            (0, 10),
            (10, 20),
            (20, 30),
            (30, 40),
            (40, 60),
            (60, 70),
            (70, 80),
            (80, 90),
            (90, 100),
        )
        for lower, upper in buckets:
            if lower <= position < upper:
                return f"{lower}-{upper}"
        if position >= 100:
            return "100+"
        return "UNKNOWN"

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        try:
            return datetime.fromisoformat(clean_display_text(value))
        except (TypeError, ValueError):
            return None
