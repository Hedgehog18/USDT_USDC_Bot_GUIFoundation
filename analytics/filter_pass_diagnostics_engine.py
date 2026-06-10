from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class FilterPassStat:
    name: str
    passed: int
    failed: int
    unknown: int
    pass_rate: float
    threshold: str


@dataclass(frozen=True)
class BlockedEntrySnapshot:
    timestamp: str
    zone: str
    work_position: float
    failed_filters: list[str]


@dataclass(frozen=True)
class FilterPassDiagnosticsSummary:
    total_entry_zone_snapshots: int
    buy_zone_snapshots: int
    sell_zone_snapshots: int
    filters: list[FilterPassStat]
    top_blocking_filters: list[tuple[str, int]]
    latest_blocked_snapshots: list[BlockedEntrySnapshot]
    warning: str | None


class FilterPassDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_summary(self, latest: int = 5) -> FilterPassDiagnosticsSummary:
        rows = self._load_entry_zone_rows()
        evaluated = [self._evaluate_row(row) for row in rows]

        filters = [
            self._build_filter_stat(evaluated, "center_confidence", "center_confidence != LOW"),
            self._build_filter_stat(
                evaluated,
                "spread_stability",
                f"0 < spread <= {self.config.max_allowed_spread}",
            ),
            self._build_filter_stat(
                evaluated,
                "market_health",
                f"market_health_score >= {self.config.min_market_health_score}",
            ),
            self._build_filter_stat(evaluated, "market_regime", "market_regime != ABNORMAL"),
            self._build_filter_stat(evaluated, "volatility_regime", "volatility_regime != EXTREME"),
            self._build_filter_stat(evaluated, "order_book_pressure", "BUY=BID_PRESSURE, SELL=ASK_PRESSURE"),
            self._build_filter_stat(evaluated, "micro_trend", "BUY=BUY_DOMINANT, SELL=SELL_DOMINANT"),
            self._build_filter_stat(evaluated, "corridor_quality", "corridor_quality_score > 0"),
            self._build_filter_stat(evaluated, "mean_reversion_score", "mean_reversion_score > 0"),
        ]

        blocked_snapshots = [
            BlockedEntrySnapshot(
                timestamp=row["timestamp"],
                zone=row["zone"],
                work_position=row["work_position"],
                failed_filters=[
                    name
                    for name, result in row["filters"].items()
                    if result is False
                ],
            )
            for row in evaluated
            if any(result is False for result in row["filters"].values())
        ]

        warning = None
        if len(rows) < 5:
            warning = "Few entry-zone samples. Run longer paper validation."

        return FilterPassDiagnosticsSummary(
            total_entry_zone_snapshots=len(rows),
            buy_zone_snapshots=sum(1 for row in rows if row["zone"] == "BUY"),
            sell_zone_snapshots=sum(1 for row in rows if row["zone"] == "SELL"),
            filters=filters,
            top_blocking_filters=self._top_blocking_filters(filters),
            latest_blocked_snapshots=list(reversed(blocked_snapshots[-latest:])),
            warning=warning,
        )

    def _load_entry_zone_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    work_position,
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
            position = float(work_position)
            result.append({
                "timestamp": clean_display_text(timestamp),
                "work_position": position,
                "zone": "BUY" if position <= self.config.buy_zone_max else "SELL",
                "spread": float(spread),
                "center_confidence": clean_display_text(center_confidence).upper(),
                "market_activity_score": float(market_activity_score),
                "market_regime": clean_display_text(market_regime).upper(),
                "order_book_pressure": clean_display_text(order_book_pressure).upper(),
                "micro_trend": clean_display_text(micro_trend).upper(),
                "volatility_regime": clean_display_text(volatility_regime).upper(),
                "corridor_quality_score": float(corridor_quality_score or 0.0),
                "mean_reversion_score": float(mean_reversion_score or 0.0),
                "market_health_score": float(market_health_score or 0.0),
                "market_health_status": clean_display_text(market_health_status).upper(),
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
    def _build_filter_stat(evaluated_rows: list[dict], name: str, threshold: str) -> FilterPassStat:
        values = [row["filters"][name] for row in evaluated_rows]
        passed = sum(1 for value in values if value is True)
        failed = sum(1 for value in values if value is False)
        unknown = sum(1 for value in values if value is None)
        evaluated = passed + failed
        pass_rate = passed / evaluated if evaluated else 0.0
        return FilterPassStat(
            name=name,
            passed=passed,
            failed=failed,
            unknown=unknown,
            pass_rate=pass_rate,
            threshold=threshold,
        )

    @staticmethod
    def _top_blocking_filters(filters: list[FilterPassStat]) -> list[tuple[str, int]]:
        return [
            (item.name, item.failed)
            for item in sorted(filters, key=lambda stat: (-stat.failed, stat.name))
            if item.failed > 0
        ]
