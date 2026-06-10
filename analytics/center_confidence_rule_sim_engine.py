from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


WORK_SHORT_ALIGNMENT_TOLERANCE = 0.00005


@dataclass(frozen=True)
class CenterConfidenceRuleProfile:
    name: str
    total_entry_zone_samples: int
    buy_candidates: int
    sell_candidates: int
    pass_count: int
    pass_rate: float
    remaining_blocking_filters: list[tuple[str, int]]
    latest_passed_samples: list["CenterConfidencePassedSample"]


@dataclass(frozen=True)
class CenterConfidencePassedSample:
    timestamp: str
    zone: str
    work_position: float
    center_confidence: str
    work_short_distance: float
    work_long_distance: float
    short_long_distance: float
    order_book_pressure: str
    micro_trend: str


@dataclass(frozen=True)
class CenterConfidenceRuleSimulationReport:
    profiles: list[CenterConfidenceRuleProfile]


class CenterConfidenceRuleSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(self, latest: int = 5) -> CenterConfidenceRuleSimulationReport:
        rows = [self._evaluate_row(row) for row in self._load_entry_zone_rows()]
        return CenterConfidenceRuleSimulationReport(
            profiles=[
                self._build_profile("strict_current", rows, "strict_current", latest),
                self._build_profile(
                    "allow_mixed_if_work_short_aligned",
                    rows,
                    "allow_mixed_if_work_short_aligned",
                    latest,
                ),
                self._build_profile(
                    "tolerate_long_lag_0_0002",
                    rows,
                    "tolerate_long_lag_0_0002",
                    latest,
                ),
                self._build_profile(
                    "tolerate_long_lag_0_0003",
                    rows,
                    "tolerate_long_lag_0_0003",
                    latest,
                ),
                self._build_profile(
                    "ignore_long_center_for_entry",
                    rows,
                    "ignore_long_center_for_entry",
                    latest,
                ),
            ]
        )

    def _build_profile(
        self,
        name: str,
        rows: list[dict],
        rule_name: str,
        latest: int,
    ) -> CenterConfidenceRuleProfile:
        blocking_filters: Counter[str] = Counter()
        passed_rows = []

        for row in rows:
            filters = dict(row["filters"])
            filters["center_confidence"] = self._profile_center_confidence_pass(row, rule_name)
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
        return CenterConfidenceRuleProfile(
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
                CenterConfidencePassedSample(
                    timestamp=row["timestamp"],
                    zone=row["zone"],
                    work_position=row["work_position"],
                    center_confidence=row["center_confidence"],
                    work_short_distance=row["work_short_distance"],
                    work_long_distance=row["work_long_distance"],
                    short_long_distance=row["short_long_distance"],
                    order_book_pressure=row["order_book_pressure"],
                    micro_trend=row["micro_trend"],
                )
                for row in reversed(passed_rows[-latest:])
            ],
        )

    def _profile_center_confidence_pass(self, row: dict, rule_name: str) -> bool:
        if row["filters"]["center_confidence"]:
            return True
        if rule_name == "strict_current":
            return False
        if rule_name == "allow_mixed_if_work_short_aligned":
            return row["work_short_distance"] <= WORK_SHORT_ALIGNMENT_TOLERANCE
        if rule_name == "tolerate_long_lag_0_0002":
            return row["work_long_distance"] <= 0.0002
        if rule_name == "tolerate_long_lag_0_0003":
            return row["work_long_distance"] <= 0.0003
        if rule_name == "ignore_long_center_for_entry":
            return row["work_short_distance"] <= WORK_SHORT_ALIGNMENT_TOLERANCE
        return False

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
                "short_long_distance": abs(short - long),
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
