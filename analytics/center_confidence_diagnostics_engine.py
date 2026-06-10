from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


CONFIDENCE_LABELS = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


@dataclass(frozen=True)
class MetricStats:
    average: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class LatestLowConfidenceSnapshot:
    timestamp: str
    work_center: float
    short_center: float
    long_center: float
    center_alignment: str
    work_position: float
    market_regime: str
    spread: float
    order_book_pressure: str


@dataclass(frozen=True)
class CenterConfidenceDiagnosticsSummary:
    total_snapshots: int
    confidence_distribution: dict[str, int]
    entry_zone_confidence_distribution: dict[str, int]
    center_zone_confidence_distribution: dict[str, int]
    work_position_stats: MetricStats
    work_center_stats: MetricStats
    short_center_stats: MetricStats
    long_center_stats: MetricStats
    center_alignment_distribution: dict[str, int]
    work_short_distance_stats: MetricStats
    work_long_distance_stats: MetricStats
    short_long_distance_stats: MetricStats
    latest_low_confidence_snapshots: list[LatestLowConfidenceSnapshot]


class CenterConfidenceDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_summary(self, latest: int = 10) -> CenterConfidenceDiagnosticsSummary:
        rows = self._load_snapshot_rows()
        entry_rows = [
            row
            for row in rows
            if row["work_position"] <= self.config.buy_zone_max
            or row["work_position"] >= self.config.sell_zone_min
        ]
        center_rows = [row for row in rows if 40.0 <= row["work_position"] <= 60.0]
        low_rows = [row for row in rows if row["center_confidence"] == "LOW"]

        return CenterConfidenceDiagnosticsSummary(
            total_snapshots=len(rows),
            confidence_distribution=self._confidence_distribution(rows),
            entry_zone_confidence_distribution=self._confidence_distribution(entry_rows),
            center_zone_confidence_distribution=self._confidence_distribution(center_rows),
            work_position_stats=self._stats([row["work_position"] for row in rows]),
            work_center_stats=self._stats([row["work_center"] for row in rows]),
            short_center_stats=self._stats([row["short_center"] for row in rows]),
            long_center_stats=self._stats([row["long_center"] for row in rows]),
            center_alignment_distribution=self._alignment_distribution(rows),
            work_short_distance_stats=self._stats([
                abs(row["work_center"] - row["short_center"]) for row in rows
            ]),
            work_long_distance_stats=self._stats([
                abs(row["work_center"] - row["long_center"]) for row in rows
            ]),
            short_long_distance_stats=self._stats([
                abs(row["short_center"] - row["long_center"]) for row in rows
            ]),
            latest_low_confidence_snapshots=[
                LatestLowConfidenceSnapshot(
                    timestamp=row["timestamp"],
                    work_center=row["work_center"],
                    short_center=row["short_center"],
                    long_center=row["long_center"],
                    center_alignment=row["center_alignment"],
                    work_position=row["work_position"],
                    market_regime=row["market_regime"],
                    spread=row["spread"],
                    order_book_pressure=row["order_book_pressure"],
                )
                for row in reversed(low_rows[-latest:])
            ],
        )

    def _load_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    work_position,
                    work_center,
                    short_center,
                    long_center,
                    center_confidence,
                    center_alignment,
                    market_regime,
                    spread,
                    order_book_pressure
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        for (
            timestamp,
            work_position,
            work_center,
            short_center,
            long_center,
            center_confidence,
            center_alignment,
            market_regime,
            spread,
            order_book_pressure,
        ) in rows:
            result.append({
                "timestamp": clean_display_text(timestamp),
                "work_position": self._float(work_position),
                "work_center": self._float(work_center),
                "short_center": self._float(short_center),
                "long_center": self._float(long_center),
                "center_confidence": self._normalize_confidence(center_confidence),
                "center_alignment": self._normalize_text(center_alignment),
                "market_regime": self._normalize_text(market_regime),
                "spread": self._float(spread),
                "order_book_pressure": self._normalize_text(order_book_pressure),
            })
        return result

    @staticmethod
    def _confidence_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter(row["center_confidence"] for row in rows)
        return {label: counter.get(label, 0) for label in CONFIDENCE_LABELS}

    @staticmethod
    def _alignment_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter(row["center_alignment"] for row in rows)
        return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))

    @staticmethod
    def _stats(values: list[float]) -> MetricStats:
        if not values:
            return MetricStats(average=0.0, minimum=0.0, maximum=0.0)
        return MetricStats(
            average=sum(values) / len(values),
            minimum=min(values),
            maximum=max(values),
        )

    @staticmethod
    def _normalize_confidence(value) -> str:
        confidence = CenterConfidenceDiagnosticsEngine._normalize_text(value)
        return confidence if confidence in CONFIDENCE_LABELS else "UNKNOWN"

    @staticmethod
    def _normalize_text(value) -> str:
        text = clean_display_text(value or "UNKNOWN").strip().upper()
        return text or "UNKNOWN"

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
