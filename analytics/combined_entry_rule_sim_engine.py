from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


WORK_SHORT_ALIGNMENT_TOLERANCE = 0.00005


@dataclass(frozen=True)
class CombinedEntryPassedSample:
    timestamp: str
    zone: str
    work_position: float
    center_confidence: str
    order_book_pressure: str
    micro_trend: str
    work_short_distance: float
    work_long_distance: float


@dataclass(frozen=True)
class CombinedEntryRuleProfile:
    name: str
    total_entry_zone_samples: int
    buy_candidates: int
    sell_candidates: int
    pass_count: int
    pass_rate: float
    remaining_blocking_filters: list[tuple[str, int]]
    latest_passed_samples: list[CombinedEntryPassedSample]


@dataclass(frozen=True)
class CombinedEntryRuleSimulationReport:
    profiles: list[CombinedEntryRuleProfile]


class CombinedEntryRuleSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(self, latest: int = 5) -> CombinedEntryRuleSimulationReport:
        rows = [self._evaluate_row(row) for row in self._load_entry_zone_rows()]
        return CombinedEntryRuleSimulationReport(
            profiles=[
                self._build_profile("strict_current", rows, latest),
                self._build_profile("relaxed_center_only", rows, latest),
                self._build_profile("relaxed_order_book_only", rows, latest),
                self._build_profile("relaxed_center_and_balanced", rows, latest),
                self._build_profile("relaxed_center_ignore_order_book", rows, latest),
                self._build_profile("entry_zone_only", rows, latest),
            ]
        )

    def _build_profile(
        self,
        name: str,
        rows: list[dict],
        latest: int,
    ) -> CombinedEntryRuleProfile:
        blocking_filters: Counter[str] = Counter()
        passed_rows = []

        for row in rows:
            filters = self._profile_filters(name, row)
            failed_filters = [
                filter_name
                for filter_name, result in filters.items()
                if result is False
            ]
            if failed_filters:
                blocking_filters.update(failed_filters)
            else:
                passed_rows.append(row)

        total = len(rows)
        return CombinedEntryRuleProfile(
            name=name,
            total_entry_zone_samples=total,
            buy_candidates=sum(1 for row in rows if row["zone"] == "BUY"),
            sell_candidates=sum(1 for row in rows if row["zone"] == "SELL"),
            pass_count=len(passed_rows),
            pass_rate=len(passed_rows) / total if total else 0.0,
            remaining_blocking_filters=sorted(
                blocking_filters.items(),
                key=lambda item: (-item[1], item[0]),
            ),
            latest_passed_samples=[
                CombinedEntryPassedSample(
                    timestamp=row["timestamp"],
                    zone=row["zone"],
                    work_position=row["work_position"],
                    center_confidence=row["center_confidence"],
                    order_book_pressure=row["order_book_pressure"],
                    micro_trend=row["micro_trend"],
                    work_short_distance=row["work_short_distance"],
                    work_long_distance=row["work_long_distance"],
                )
                for row in reversed(passed_rows[-latest:])
            ],
        )

    def _profile_filters(self, name: str, row: dict) -> dict[str, bool | None]:
        filters = dict(row["filters"])

        if name in {
            "relaxed_center_only",
            "relaxed_center_and_balanced",
            "relaxed_center_ignore_order_book",
        }:
            filters["center_confidence"] = self._relaxed_center_pass(row)

        if name in {"relaxed_order_book_only", "relaxed_center_and_balanced"}:
            filters["order_book_pressure"] = self._allow_balanced_order_book_pass(row)

        if name == "relaxed_center_ignore_order_book":
            filters["order_book_pressure"] = True

        if name == "entry_zone_only":
            return {
                "spread_stability": filters["spread_stability"],
                "market_health": filters["market_health"],
                "market_regime": filters["market_regime"],
                "volatility_regime": filters["volatility_regime"],
            }

        return filters

    def _relaxed_center_pass(self, row: dict) -> bool:
        return (
            row["filters"]["center_confidence"]
            or row["work_short_distance"] <= WORK_SHORT_ALIGNMENT_TOLERANCE
            or row["work_long_distance"] <= 0.0003
        )

    @staticmethod
    def _allow_balanced_order_book_pass(row: dict) -> bool | None:
        pressure = row["order_book_pressure"]
        if not pressure or pressure == "UNKNOWN":
            return None
        if pressure == "BALANCED":
            return True
        if row["zone"] == "BUY":
            return pressure == "BID_PRESSURE"
        return pressure == "ASK_PRESSURE"

    def _load_entry_zone_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    work_position,
                    work_center,
                    short_center,
                    long_center,
                    spread,
                    center_confidence,
                    market_activity_score,
                    market_regime,
                    order_book_pressure,
                    micro_trend,
                    volatility_regime,
                    corridor_quality_score,
                    mean_reversion_score,
                    market_health_score,
                    market_health_status
                FROM market_snapshots
                WHERE work_position <= ? OR work_position >= ?
                ORDER BY timestamp ASC
                """,
                (self.config.buy_zone_max, self.config.sell_zone_min),
            ).fetchall()

        result = []
        for row in rows:
            (
                timestamp,
                work_position,
                work_center,
                short_center,
                long_center,
                spread,
                center_confidence,
                market_activity_score,
                market_regime,
                order_book_pressure,
                micro_trend,
                volatility_regime,
                corridor_quality_score,
                mean_reversion_score,
                market_health_score,
                market_health_status,
            ) = row
            position = self._float(work_position)
            work = self._float(work_center)
            short = self._float(short_center)
            long = self._float(long_center)
            result.append({
                "timestamp": clean_display_text(timestamp),
                "work_position": position,
                "zone": "BUY" if position <= self.config.buy_zone_max else "SELL",
                "work_center": work,
                "short_center": short,
                "long_center": long,
                "work_short_distance": abs(work - short),
                "work_long_distance": abs(work - long),
                "spread": self._float(spread),
                "center_confidence": self._text(center_confidence),
                "market_activity_score": self._float(market_activity_score),
                "market_regime": self._text(market_regime),
                "order_book_pressure": self._text(order_book_pressure),
                "micro_trend": self._text(micro_trend),
                "volatility_regime": self._text(volatility_regime),
                "corridor_quality_score": self._float(corridor_quality_score),
                "mean_reversion_score": self._float(mean_reversion_score),
                "market_health_score": self._float(market_health_score),
                "market_health_status": self._text(market_health_status),
            })
        return result

    def _evaluate_row(self, row: dict) -> dict:
        zone = row["zone"]
        return {
            **row,
            "filters": {
                "center_confidence": row["center_confidence"] not in {"LOW", "UNKNOWN", ""},
                "spread_stability": 0.0 < row["spread"] <= self.config.max_allowed_spread,
                "market_health": (
                    row["market_health_score"] >= self.config.min_market_health_score
                    and row["market_health_status"] != "UNHEALTHY"
                ),
                "market_regime": row["market_regime"] != "ABNORMAL",
                "volatility_regime": row["volatility_regime"] != "EXTREME",
                "order_book_pressure": self._order_book_pressure_pass(zone, row["order_book_pressure"]),
                "micro_trend": self._micro_trend_pass(zone, row["micro_trend"]),
                "corridor_quality": row["corridor_quality_score"] > 0.0,
                "mean_reversion_score": row["mean_reversion_score"] > 0.0,
            },
        }

    @staticmethod
    def _order_book_pressure_pass(zone: str, pressure: str) -> bool | None:
        if not pressure or pressure == "UNKNOWN":
            return None
        if zone == "BUY":
            return pressure == "BID_PRESSURE"
        return pressure == "ASK_PRESSURE"

    @staticmethod
    def _micro_trend_pass(zone: str, micro_trend: str) -> bool | None:
        if not micro_trend or micro_trend == "UNKNOWN":
            return None
        if zone == "BUY":
            return micro_trend == "BUY_DOMINANT"
        return micro_trend == "SELL_DOMINANT"

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
