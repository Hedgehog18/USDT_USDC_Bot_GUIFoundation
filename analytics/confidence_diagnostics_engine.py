from collections import Counter
from dataclasses import dataclass
from statistics import median

from analytics.strategy_validation_engine import CONFIDENCE_SCORES
from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


BUCKETS = (
    ("0.0-0.2", 0.0, 0.2),
    ("0.2-0.4", 0.2, 0.4),
    ("0.4-0.6", 0.4, 0.6),
    ("0.6-0.8", 0.6, 0.8),
    ("0.8-1.0", 0.8, 1.0),
)


@dataclass(frozen=True)
class CenterDistanceStats:
    average: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class ConfidenceDiagnosticsSummary:
    total_decisions: int
    average_confidence: float
    min_confidence: float
    max_confidence: float
    median_confidence: float
    confidence_buckets: dict[str, int]
    top_wait_reasons: list[tuple[str, int]]
    center_distance: CenterDistanceStats
    market_regime_distribution: dict[str, int]


class ConfidenceDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self, top: int = 5) -> ConfidenceDiagnosticsSummary:
        signal_rows = self._load_signal_rows()
        confidence_scores = [self._confidence_to_score(row["confidence"]) for row in signal_rows]
        center_distances = self._load_center_distances()

        return ConfidenceDiagnosticsSummary(
            total_decisions=len(signal_rows),
            average_confidence=self._average(confidence_scores),
            min_confidence=min(confidence_scores) if confidence_scores else 0.0,
            max_confidence=max(confidence_scores) if confidence_scores else 0.0,
            median_confidence=median(confidence_scores) if confidence_scores else 0.0,
            confidence_buckets=self._build_buckets(confidence_scores),
            top_wait_reasons=self._top_wait_reasons(signal_rows, top),
            center_distance=CenterDistanceStats(
                average=self._average(center_distances),
                minimum=min(center_distances) if center_distances else 0.0,
                maximum=max(center_distances) if center_distances else 0.0,
            ),
            market_regime_distribution=self._load_market_regime_distribution(),
        )

    def _load_signal_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT action, reason, confidence
                FROM trade_signals
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            {
                "action": clean_display_text(action),
                "reason": clean_display_text(reason),
                "confidence": clean_display_text(confidence),
            }
            for action, reason, confidence in rows
        ]

    def _load_center_distances(self) -> list[float]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT work_position
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

            if not rows:
                rows = conn.execute(
                    """
                    SELECT work_position
                    FROM decision_audit
                    ORDER BY timestamp ASC
                    """
                ).fetchall()

        return [abs(float(row[0]) - 50.0) for row in rows]

    def _load_market_regime_distribution(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT market_regime, COUNT(*)
                FROM market_snapshots
                GROUP BY market_regime
                ORDER BY COUNT(*) DESC, market_regime ASC
                """
            ).fetchall()

            if not rows:
                rows = conn.execute(
                    """
                    SELECT market_regime, COUNT(*)
                    FROM decision_audit
                    GROUP BY market_regime
                    ORDER BY COUNT(*) DESC, market_regime ASC
                    """
                ).fetchall()

        return {clean_display_text(regime): int(count) for regime, count in rows}

    @staticmethod
    def _confidence_to_score(confidence: str) -> float:
        raw_value = str(confidence).strip()
        if not raw_value:
            return 0.0

        try:
            value = float(raw_value)
            return min(1.0, max(0.0, value))
        except ValueError:
            pass

        normalized = raw_value.upper().replace(" ", "_").replace("-", "_")
        return CONFIDENCE_SCORES.get(normalized, 0.0)

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _build_buckets(values: list[float]) -> dict[str, int]:
        bucket_counts = {label: 0 for label, _lower, _upper in BUCKETS}
        for value in values:
            for label, lower, upper in BUCKETS:
                if lower <= value < upper or (label == "0.8-1.0" and value == 1.0):
                    bucket_counts[label] += 1
                    break
        return bucket_counts

    @staticmethod
    def _top_wait_reasons(rows: list[dict], top: int) -> list[tuple[str, int]]:
        counter = Counter(
            row["reason"] or "No reason"
            for row in rows
            if ConfidenceDiagnosticsEngine._is_wait(row["action"])
        )
        return counter.most_common(top)

    @staticmethod
    def _is_wait(action: str) -> bool:
        value = str(action).upper()
        return value == "WAIT" or value == "SAFE_WAIT" or value.endswith("WAIT")
