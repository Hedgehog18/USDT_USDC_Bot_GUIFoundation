from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


DEFAULT_POST_ENTRY_HORIZONS = (1, 3, 5, 10, 20, 30)
SUPPORTED_POST_ENTRY_PROFILES = ("mean_reversion_v1", "mean_reversion_v2")


@dataclass(frozen=True)
class PostEntryPathCandidate:
    timestamp: str
    direction: str
    entry_price: float
    target_price: float
    work_position: float
    micro_trend: str
    next_prices: list[tuple[int, float | None]]
    max_favorable_movement: float | None
    max_adverse_movement: float | None
    time_to_best_favorable_movement: int | None
    did_hit_target: bool
    did_move_halfway_to_target: bool
    did_reverse_against_entry: bool
    failure_mode: str


@dataclass(frozen=True)
class PostEntryPathSummary:
    candidates_count: int
    hit_target_rate: float
    halfway_to_target_rate: float
    average_max_favorable_movement: float | None
    average_max_adverse_movement: float | None
    average_time_to_best_favorable_movement: float | None
    common_failure_mode: str
    failure_modes: list[tuple[str, int]]


@dataclass(frozen=True)
class PostEntryPathDiagnosticsReport:
    profile: str
    target_profit: float
    horizons: tuple[int, ...]
    candidates: list[PostEntryPathCandidate]
    summary: PostEntryPathSummary


class PostEntryPathDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(
        self,
        *,
        profile: str = "mean_reversion_v2",
        horizons: tuple[int, ...] = DEFAULT_POST_ENTRY_HORIZONS,
    ) -> PostEntryPathDiagnosticsReport:
        if profile not in SUPPORTED_POST_ENTRY_PROFILES:
            supported = ", ".join(SUPPORTED_POST_ENTRY_PROFILES)
            raise ValueError(f"Unsupported post-entry profile: {profile}. Supported: {supported}")

        snapshots = self._load_snapshot_rows()
        max_horizon = max(horizons) if horizons else 0
        candidates = [
            self._build_candidate(snapshots, index, direction, horizons, max_horizon)
            for index, snapshot in enumerate(snapshots)
            for direction in [self._entry_direction(snapshot, profile)]
            if direction in {"BUY_USDC", "SELL_USDC"} and index + 1 < len(snapshots)
        ]

        return PostEntryPathDiagnosticsReport(
            profile=profile,
            target_profit=self.config.target_profit,
            horizons=horizons,
            candidates=candidates,
            summary=self._build_summary(candidates),
        )

    def _build_candidate(
        self,
        snapshots: list[dict],
        index: int,
        direction: str,
        horizons: tuple[int, ...],
        max_horizon: int,
    ) -> PostEntryPathCandidate:
        snapshot = snapshots[index]
        future = snapshots[index + 1 : index + max_horizon + 1]
        entry_price = snapshot["price"]
        target_price = self._target_price(direction, entry_price)
        halfway_price = entry_price + ((target_price - entry_price) / 2.0)
        target_distance = abs(target_price - entry_price)
        reverse_threshold = max(target_distance / 2.0, 0.00000001)

        movements = [
            self._movement_in_expected_direction(
                direction,
                entry_price=entry_price,
                future_price=future_snapshot["price"],
            )
            for future_snapshot in future
        ]
        max_favorable = max(movements) if movements else None
        max_adverse = min(movements) if movements else None
        time_to_best = (
            movements.index(max_favorable) + 1
            if movements and max_favorable is not None
            else None
        )
        hit_target = any(
            self._target_hit(direction, future_snapshot["price"], target_price)
            for future_snapshot in future
        )
        halfway_hit = any(
            self._target_hit(direction, future_snapshot["price"], halfway_price)
            for future_snapshot in future
        )
        reversed_against_entry = any(movement <= -reverse_threshold for movement in movements)

        return PostEntryPathCandidate(
            timestamp=snapshot["timestamp"],
            direction=direction,
            entry_price=entry_price,
            target_price=target_price,
            work_position=snapshot["work_position"],
            micro_trend=snapshot["micro_trend"],
            next_prices=[
                (
                    horizon,
                    snapshots[index + horizon]["price"]
                    if index + horizon < len(snapshots)
                    else None,
                )
                for horizon in horizons
            ],
            max_favorable_movement=max_favorable,
            max_adverse_movement=max_adverse,
            time_to_best_favorable_movement=time_to_best,
            did_hit_target=hit_target,
            did_move_halfway_to_target=halfway_hit,
            did_reverse_against_entry=reversed_against_entry,
            failure_mode=self._failure_mode(
                hit_target=hit_target,
                halfway_hit=halfway_hit,
                reversed_against_entry=reversed_against_entry,
                max_favorable=max_favorable,
                target_distance=target_distance,
            ),
        )

    def _build_summary(self, candidates: list[PostEntryPathCandidate]) -> PostEntryPathSummary:
        if not candidates:
            return PostEntryPathSummary(
                candidates_count=0,
                hit_target_rate=0.0,
                halfway_to_target_rate=0.0,
                average_max_favorable_movement=None,
                average_max_adverse_movement=None,
                average_time_to_best_favorable_movement=None,
                common_failure_mode="no candidates",
                failure_modes=[],
            )

        favorable = [
            item.max_favorable_movement
            for item in candidates
            if item.max_favorable_movement is not None
        ]
        adverse = [
            item.max_adverse_movement
            for item in candidates
            if item.max_adverse_movement is not None
        ]
        time_to_best = [
            item.time_to_best_favorable_movement
            for item in candidates
            if item.time_to_best_favorable_movement is not None
        ]
        failure_modes = Counter(item.failure_mode for item in candidates if not item.did_hit_target)
        sorted_failures = sorted(failure_modes.items(), key=lambda item: (-item[1], item[0]))

        return PostEntryPathSummary(
            candidates_count=len(candidates),
            hit_target_rate=sum(1 for item in candidates if item.did_hit_target) / len(candidates),
            halfway_to_target_rate=(
                sum(1 for item in candidates if item.did_move_halfway_to_target) / len(candidates)
            ),
            average_max_favorable_movement=self._average(favorable),
            average_max_adverse_movement=self._average(adverse),
            average_time_to_best_favorable_movement=self._average(time_to_best),
            common_failure_mode=sorted_failures[0][0] if sorted_failures else "target hit",
            failure_modes=sorted_failures,
        )

    def _entry_direction(self, row: dict, profile: str) -> str:
        buy_zone_max = 25.0 if profile == "mean_reversion_v2" else self.config.buy_zone_max
        sell_zone_min = 75.0 if profile == "mean_reversion_v2" else self.config.sell_zone_min

        if not (0.0 < row["spread"] <= self.config.max_allowed_spread):
            return "WAIT"
        if (
            row["market_health_score"] < self.config.min_market_health_score
            or row["market_health_status"] == "UNHEALTHY"
        ):
            return "WAIT"
        if row["market_regime"] == "ABNORMAL" or row["volatility_regime"] == "EXTREME":
            return "WAIT"

        if row["work_position"] <= buy_zone_max and row["micro_trend"] == "BUY_DOMINANT":
            return "BUY_USDC"
        if row["work_position"] >= sell_zone_min and row["micro_trend"] == "SELL_DOMINANT":
            return "SELL_USDC"
        return "WAIT"

    def _load_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    price,
                    work_position,
                    spread,
                    market_regime,
                    micro_trend,
                    volatility_regime,
                    market_health_score,
                    market_health_status
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            {
                "timestamp": clean_display_text(timestamp),
                "price": self._float(price),
                "work_position": self._float(work_position),
                "spread": self._float(spread),
                "market_regime": self._text(market_regime),
                "micro_trend": self._text(micro_trend),
                "volatility_regime": self._text(volatility_regime),
                "market_health_score": self._float(market_health_score),
                "market_health_status": self._text(market_health_status),
            }
            for (
                timestamp,
                price,
                work_position,
                spread,
                market_regime,
                micro_trend,
                volatility_regime,
                market_health_score,
                market_health_status,
            ) in rows
        ]

    def _target_price(self, direction: str, entry_price: float) -> float:
        if direction == "BUY_USDC":
            return entry_price * (1 + self.config.target_profit)
        return entry_price * (1 - self.config.target_profit)

    @staticmethod
    def _target_hit(direction: str, price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return price >= target_price
        if direction == "SELL_USDC":
            return price <= target_price
        return False

    @staticmethod
    def _movement_in_expected_direction(direction: str, entry_price: float, future_price: float) -> float:
        if direction == "BUY_USDC":
            return future_price - entry_price
        if direction == "SELL_USDC":
            return entry_price - future_price
        return future_price - entry_price

    @staticmethod
    def _failure_mode(
        *,
        hit_target: bool,
        halfway_hit: bool,
        reversed_against_entry: bool,
        max_favorable: float | None,
        target_distance: float,
    ) -> str:
        if hit_target:
            return "target hit"
        if reversed_against_entry:
            return "immediate adverse move"
        if max_favorable is None or abs(max_favorable) < 0.00000001:
            return "no movement"
        if halfway_hit or max_favorable >= target_distance * 0.5:
            return "target too far"
        return "no movement"

    @staticmethod
    def _average(values: list[float | int]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
