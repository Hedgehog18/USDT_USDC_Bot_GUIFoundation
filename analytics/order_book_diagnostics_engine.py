from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


PRESSURE_LABELS = ("BALANCED", "BID_PRESSURE", "ASK_PRESSURE", "UNKNOWN")


@dataclass(frozen=True)
class LatestOrderBookEntrySnapshot:
    timestamp: str
    direction_candidate: str
    work_position: float
    order_book_pressure: str
    order_book_imbalance: float
    micro_trend: str
    center_confidence: str


@dataclass(frozen=True)
class OrderBookDiagnosticsSummary:
    total_snapshots: int
    entry_zone_snapshots: int
    order_book_pressure_distribution: dict[str, int]
    buy_zone_distribution: dict[str, int]
    sell_zone_distribution: dict[str, int]
    average_order_book_imbalance: float
    min_order_book_imbalance: float
    max_order_book_imbalance: float
    latest_entry_zone_snapshots: list[LatestOrderBookEntrySnapshot]


class OrderBookDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_summary(self, latest: int = 10) -> OrderBookDiagnosticsSummary:
        rows = self._load_snapshot_rows()
        entry_rows = [
            row
            for row in rows
            if row["work_position"] <= self.config.buy_zone_max
            or row["work_position"] >= self.config.sell_zone_min
        ]
        imbalances = [row["order_book_imbalance"] for row in entry_rows]

        return OrderBookDiagnosticsSummary(
            total_snapshots=len(rows),
            entry_zone_snapshots=len(entry_rows),
            order_book_pressure_distribution=self._pressure_distribution(rows),
            buy_zone_distribution=self._zone_distribution(
                [row for row in entry_rows if row["direction_candidate"] == "BUY"]
            ),
            sell_zone_distribution=self._zone_distribution(
                [row for row in entry_rows if row["direction_candidate"] == "SELL"]
            ),
            average_order_book_imbalance=self._average(imbalances),
            min_order_book_imbalance=min(imbalances) if imbalances else 0.0,
            max_order_book_imbalance=max(imbalances) if imbalances else 0.0,
            latest_entry_zone_snapshots=[
                LatestOrderBookEntrySnapshot(
                    timestamp=row["timestamp"],
                    direction_candidate=row["direction_candidate"],
                    work_position=row["work_position"],
                    order_book_pressure=row["order_book_pressure"],
                    order_book_imbalance=row["order_book_imbalance"],
                    micro_trend=row["micro_trend"],
                    center_confidence=row["center_confidence"],
                )
                for row in reversed(entry_rows[-latest:])
            ],
        )

    def _load_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    work_position,
                    order_book_pressure,
                    order_book_imbalance,
                    micro_trend,
                    center_confidence
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        for (
            timestamp,
            work_position,
            order_book_pressure,
            order_book_imbalance,
            micro_trend,
            center_confidence,
        ) in rows:
            position = float(work_position)
            result.append({
                "timestamp": clean_display_text(timestamp),
                "work_position": position,
                "direction_candidate": self._direction_candidate(position),
                "order_book_pressure": self._normalize_pressure(order_book_pressure),
                "order_book_imbalance": float(order_book_imbalance or 0.0),
                "micro_trend": clean_display_text(micro_trend or "UNKNOWN").upper(),
                "center_confidence": clean_display_text(center_confidence or "UNKNOWN").upper(),
            })
        return result

    def _direction_candidate(self, work_position: float) -> str:
        if work_position <= self.config.buy_zone_max:
            return "BUY"
        if work_position >= self.config.sell_zone_min:
            return "SELL"
        return "CENTER"

    @staticmethod
    def _normalize_pressure(value) -> str:
        pressure = clean_display_text(value or "UNKNOWN").upper()
        return pressure if pressure in PRESSURE_LABELS else "UNKNOWN"

    @staticmethod
    def _pressure_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter(row["order_book_pressure"] for row in rows)
        return {label: counter.get(label, 0) for label in PRESSURE_LABELS}

    @staticmethod
    def _zone_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter(row["order_book_pressure"] for row in rows)
        return {
            "BID_PRESSURE": counter.get("BID_PRESSURE", 0),
            "ASK_PRESSURE": counter.get("ASK_PRESSURE", 0),
            "BALANCED": counter.get("BALANCED", 0),
            "UNKNOWN": counter.get("UNKNOWN", 0),
        }

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0
