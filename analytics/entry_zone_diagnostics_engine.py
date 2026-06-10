from collections import Counter
from dataclasses import dataclass
from statistics import median

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


POSITION_BUCKETS = (
    ("0-10", 0.0, 10.0),
    ("10-20", 10.0, 20.0),
    ("20-30", 20.0, 30.0),
    ("30-40", 30.0, 40.0),
    ("40-60", 40.0, 60.0),
    ("60-70", 60.0, 70.0),
    ("70-80", 70.0, 80.0),
    ("80-90", 80.0, 90.0),
    ("90-100", 90.0, 100.0),
)


@dataclass(frozen=True)
class EntryZoneDiagnosticsSummary:
    total_snapshots: int
    average_work_position: float
    min_work_position: float
    max_work_position: float
    median_work_position: float
    buckets: dict[str, int]
    potential_buy_zone_count: int
    potential_sell_zone_count: int
    center_zone_count: int
    average_spread: float
    average_market_health_score: float
    market_regime_distribution: dict[str, int]


class EntryZoneDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self) -> EntryZoneDiagnosticsSummary:
        rows = self._load_market_snapshot_rows()
        positions = [row["work_position"] for row in rows]
        spreads = [row["spread"] for row in rows]
        health_scores = [row["market_health_score"] for row in rows]

        return EntryZoneDiagnosticsSummary(
            total_snapshots=len(rows),
            average_work_position=self._average(positions),
            min_work_position=min(positions) if positions else 0.0,
            max_work_position=max(positions) if positions else 0.0,
            median_work_position=median(positions) if positions else 0.0,
            buckets=self._build_buckets(positions),
            potential_buy_zone_count=sum(1 for value in positions if value <= 20.0),
            potential_sell_zone_count=sum(1 for value in positions if value >= 80.0),
            center_zone_count=sum(1 for value in positions if 40.0 <= value <= 60.0),
            average_spread=self._average(spreads),
            average_market_health_score=self._average(health_scores),
            market_regime_distribution=self._market_regime_distribution(rows),
        )

    def _load_market_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT work_position, spread, market_health_score, market_regime
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            {
                "work_position": float(work_position),
                "spread": float(spread),
                "market_health_score": float(market_health_score or 0.0),
                "market_regime": clean_display_text(market_regime),
            }
            for work_position, spread, market_health_score, market_regime in rows
        ]

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _build_buckets(values: list[float]) -> dict[str, int]:
        bucket_counts = {label: 0 for label, _lower, _upper in POSITION_BUCKETS}
        for value in values:
            for label, lower, upper in POSITION_BUCKETS:
                if lower <= value < upper or (label == "90-100" and value == 100.0):
                    bucket_counts[label] += 1
                    break
        return bucket_counts

    @staticmethod
    def _market_regime_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter(row["market_regime"] or "UNKNOWN" for row in rows)
        return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
