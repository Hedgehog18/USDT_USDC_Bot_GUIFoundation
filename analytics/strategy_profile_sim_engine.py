from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


SUPPORTED_STRATEGY_PROFILES = (
    "strict_current",
    "mean_reversion_v1",
    "mean_reversion_v2",
    "mean_reversion_v2_small_target",
    "mean_reversion_v2_small_target_ny",
)


@dataclass(frozen=True)
class StrategyProfileCandidate:
    timestamp: str
    direction: str
    work_position: float
    spread: float
    market_health_score: float
    market_regime: str
    volatility_regime: str
    micro_trend: str
    center_confidence: str
    order_book_pressure: str


@dataclass(frozen=True)
class StrategyProfileSimulationReport:
    profile: str
    total_snapshots: int
    total_entry_zone_samples: int
    buy_candidates: int
    sell_candidates: int
    pass_count: int
    pass_rate: float
    remaining_blocking_filters: list[tuple[str, int]]
    latest_candidates: list[StrategyProfileCandidate]


class StrategyProfileSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(
        self,
        profile: str = "strict_current",
        latest: int = 10,
    ) -> StrategyProfileSimulationReport:
        if profile not in SUPPORTED_STRATEGY_PROFILES:
            supported = ", ".join(SUPPORTED_STRATEGY_PROFILES)
            raise ValueError(f"Unsupported strategy profile: {profile}. Supported: {supported}")

        rows = [self._evaluate_row(row, profile) for row in self._load_snapshot_rows()]
        entry_rows = [row for row in rows if row["zone"] in {"BUY", "SELL"}]
        passed_rows = []
        blocking_filters: Counter[str] = Counter()

        for row in entry_rows:
            filters = self._profile_filters(profile, row)
            failed_filters = [
                filter_name
                for filter_name, result in filters.items()
                if result is False
            ]
            if failed_filters:
                blocking_filters.update(failed_filters)
            else:
                passed_rows.append(row)

        return StrategyProfileSimulationReport(
            profile=profile,
            total_snapshots=len(rows),
            total_entry_zone_samples=len(entry_rows),
            buy_candidates=sum(1 for row in passed_rows if row["zone"] == "BUY"),
            sell_candidates=sum(1 for row in passed_rows if row["zone"] == "SELL"),
            pass_count=len(passed_rows),
            pass_rate=len(passed_rows) / len(entry_rows) if entry_rows else 0.0,
            remaining_blocking_filters=sorted(
                blocking_filters.items(),
                key=lambda item: (-item[1], item[0]),
            ),
            latest_candidates=[
                StrategyProfileCandidate(
                    timestamp=row["timestamp"],
                    direction=row["zone"],
                    work_position=row["work_position"],
                    spread=row["spread"],
                    market_health_score=row["market_health_score"],
                    market_regime=row["market_regime"],
                    volatility_regime=row["volatility_regime"],
                    micro_trend=row["micro_trend"],
                    center_confidence=row["center_confidence"],
                    order_book_pressure=row["order_book_pressure"],
                )
                for row in reversed(passed_rows[-latest:])
            ],
        )

    def _profile_filters(self, profile: str, row: dict) -> dict[str, bool | None]:
        if profile in {"mean_reversion_v1", "mean_reversion_v2", "mean_reversion_v2_small_target", "mean_reversion_v2_small_target_ny"}:
            filters = {
                "spread_stability": row["filters"]["spread_stability"],
                "market_health": row["filters"]["market_health"],
                "market_regime": row["filters"]["market_regime"],
                "volatility_regime": row["filters"]["volatility_regime"],
                "micro_trend": row["filters"]["micro_trend"],
            }
            if profile == "mean_reversion_v2_small_target_ny":
                filters["new_york_session"] = row["filters"]["new_york_session"]
            return filters
        return dict(row["filters"])

    def _load_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    work_position,
                    spread,
                    center_confidence,
                    market_regime,
                    order_book_pressure,
                    micro_trend,
                    volatility_regime,
                    corridor_quality_score,
                    mean_reversion_score,
                    market_health_score,
                    market_health_status
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        for row in rows:
            (
                timestamp,
                work_position,
                spread,
                center_confidence,
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
            result.append({
                "timestamp": clean_display_text(timestamp),
                "work_position": position,
                "spread": self._float(spread),
                "center_confidence": self._text(center_confidence),
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

    def _evaluate_row(self, row: dict, profile: str) -> dict:
        zone = self._zone(row["work_position"], profile)
        return {
            **row,
            "zone": zone,
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
                "new_york_session": self._is_new_york_session(row["timestamp"]),
                "corridor_quality": row["corridor_quality_score"] > 0.0,
                "mean_reversion_score": row["mean_reversion_score"] > 0.0,
            },
        }

    def _zone(self, work_position: float, profile: str) -> str:
        uses_v2_zones = profile in {"mean_reversion_v2", "mean_reversion_v2_small_target", "mean_reversion_v2_small_target_ny"}
        buy_zone_max = 25.0 if uses_v2_zones else self.config.buy_zone_max
        sell_zone_min = 75.0 if uses_v2_zones else self.config.sell_zone_min
        if work_position <= buy_zone_max:
            return "BUY"
        if work_position >= sell_zone_min:
            return "SELL"
        return "CENTER"

    @staticmethod
    def _order_book_pressure_pass(zone: str, pressure: str) -> bool | None:
        if zone not in {"BUY", "SELL"}:
            return True
        if not pressure or pressure == "UNKNOWN":
            return None
        if zone == "BUY":
            return pressure == "BID_PRESSURE"
        return pressure == "ASK_PRESSURE"

    @staticmethod
    def _micro_trend_pass(zone: str, micro_trend: str) -> bool | None:
        if zone not in {"BUY", "SELL"}:
            return True
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

    @staticmethod
    def _is_new_york_session(timestamp: str) -> bool:
        from datetime import datetime

        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return False
        return 17 <= parsed.hour <= 23
