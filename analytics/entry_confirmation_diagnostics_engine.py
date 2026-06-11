from __future__ import annotations

from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


DEFAULT_ENTRY_CONFIRMATION_HORIZON = 30
SUPPORTED_ENTRY_CONFIRMATION_PROFILES = ("mean_reversion_v1", "mean_reversion_v2")
ENTRY_CONFIRMATION_VARIANTS = (
    "immediate_entry",
    "wait_1_snapshot",
    "wait_2_snapshots",
    "require_price_turn",
    "require_micro_trend_persistence",
)


@dataclass(frozen=True)
class EntryConfirmationResult:
    variant: str
    base_candidate_count: int
    candidate_count: int
    hit_target_count: int
    hit_target_rate: float
    halfway_count: int
    halfway_rate: float
    immediate_adverse_move_count: int
    immediate_adverse_move_rate: float
    average_favorable_movement: float | None
    average_adverse_movement: float | None
    missed_opportunities_count: int
    recommendation_score: float


@dataclass(frozen=True)
class EntryConfirmationDiagnosticsReport:
    profile: str
    target_profit: float
    horizon: int
    results: list[EntryConfirmationResult]


class EntryConfirmationDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(
        self,
        *,
        profile: str = "mean_reversion_v2",
        horizon: int = DEFAULT_ENTRY_CONFIRMATION_HORIZON,
    ) -> EntryConfirmationDiagnosticsReport:
        if profile not in SUPPORTED_ENTRY_CONFIRMATION_PROFILES:
            supported = ", ".join(SUPPORTED_ENTRY_CONFIRMATION_PROFILES)
            raise ValueError(f"Unsupported entry confirmation profile: {profile}. Supported: {supported}")

        snapshots = self._load_snapshot_rows()
        base_candidates = [
            (index, snapshot, self._entry_direction(snapshot, profile))
            for index, snapshot in enumerate(snapshots)
            for direction in [self._entry_direction(snapshot, profile)]
            if direction in {"BUY_USDC", "SELL_USDC"} and index + 1 < len(snapshots)
        ]

        return EntryConfirmationDiagnosticsReport(
            profile=profile,
            target_profit=self.config.target_profit,
            horizon=horizon,
            results=[
                self._evaluate_variant(snapshots, base_candidates, variant, horizon)
                for variant in ENTRY_CONFIRMATION_VARIANTS
            ],
        )

    def _evaluate_variant(
        self,
        snapshots: list[dict],
        base_candidates: list[tuple[int, dict, str]],
        variant: str,
        horizon: int,
    ) -> EntryConfirmationResult:
        entered: list[tuple[int, dict, str]] = []
        for index, snapshot, direction in base_candidates:
            entry_index = self._entry_index_for_variant(snapshots, index, direction, variant)
            if entry_index is None or entry_index >= len(snapshots):
                continue
            entered.append((entry_index, snapshots[entry_index], direction))

        hit_count = 0
        halfway_count = 0
        adverse_count = 0
        favorable_movements: list[float] = []
        adverse_movements: list[float] = []

        for entry_index, entry_snapshot, direction in entered:
            path = self._path_metrics(snapshots, entry_index, direction, horizon)
            if path["hit_target"]:
                hit_count += 1
            if path["halfway_hit"]:
                halfway_count += 1
            if path["immediate_adverse"]:
                adverse_count += 1
            if path["max_favorable"] is not None:
                favorable_movements.append(path["max_favorable"])
            if path["max_adverse"] is not None:
                adverse_movements.append(path["max_adverse"])

        candidate_count = len(entered)
        hit_rate = hit_count / candidate_count if candidate_count else 0.0
        halfway_rate = halfway_count / candidate_count if candidate_count else 0.0
        adverse_rate = adverse_count / candidate_count if candidate_count else 0.0
        avg_favorable = self._average(favorable_movements)
        avg_adverse = self._average(adverse_movements)

        return EntryConfirmationResult(
            variant=variant,
            base_candidate_count=len(base_candidates),
            candidate_count=candidate_count,
            hit_target_count=hit_count,
            hit_target_rate=hit_rate,
            halfway_count=halfway_count,
            halfway_rate=halfway_rate,
            immediate_adverse_move_count=adverse_count,
            immediate_adverse_move_rate=adverse_rate,
            average_favorable_movement=avg_favorable,
            average_adverse_movement=avg_adverse,
            missed_opportunities_count=len(base_candidates) - candidate_count,
            recommendation_score=self._recommendation_score(
                hit_rate=hit_rate,
                halfway_rate=halfway_rate,
                adverse_rate=adverse_rate,
                candidate_count=candidate_count,
                base_candidate_count=len(base_candidates),
                average_favorable=avg_favorable,
                average_adverse=avg_adverse,
            ),
        )

    def _entry_index_for_variant(
        self,
        snapshots: list[dict],
        index: int,
        direction: str,
        variant: str,
    ) -> int | None:
        if variant == "immediate_entry":
            return index
        if variant == "wait_1_snapshot":
            return index + 1 if index + 1 < len(snapshots) else None
        if variant == "wait_2_snapshots":
            return index + 2 if index + 2 < len(snapshots) else None
        if variant == "require_price_turn":
            next_index = index + 1
            if next_index >= len(snapshots):
                return None
            entry_price = snapshots[index]["price"]
            next_price = snapshots[next_index]["price"]
            if direction == "BUY_USDC" and next_price > entry_price:
                return next_index
            if direction == "SELL_USDC" and next_price < entry_price:
                return next_index
            return None
        if variant == "require_micro_trend_persistence":
            next_index = index + 1
            if next_index >= len(snapshots):
                return None
            required = "BUY_DOMINANT" if direction == "BUY_USDC" else "SELL_DOMINANT"
            if snapshots[next_index]["micro_trend"] == required:
                return next_index
            return None
        raise ValueError(f"Unsupported entry confirmation variant: {variant}")

    def _path_metrics(
        self,
        snapshots: list[dict],
        entry_index: int,
        direction: str,
        horizon: int,
    ) -> dict:
        entry_price = snapshots[entry_index]["price"]
        target_price = self._target_price(direction, entry_price)
        halfway_price = entry_price + ((target_price - entry_price) / 2.0)
        target_distance = abs(target_price - entry_price)
        reverse_threshold = max(target_distance / 2.0, 0.00000001)
        future = snapshots[entry_index + 1 : entry_index + horizon + 1]
        movements = [
            self._movement_in_expected_direction(
                direction,
                entry_price=entry_price,
                future_price=future_snapshot["price"],
            )
            for future_snapshot in future
        ]

        return {
            "hit_target": any(
                self._target_hit(direction, future_snapshot["price"], target_price)
                for future_snapshot in future
            ),
            "halfway_hit": any(
                self._target_hit(direction, future_snapshot["price"], halfway_price)
                for future_snapshot in future
            ),
            "immediate_adverse": bool(movements and movements[0] <= -reverse_threshold),
            "max_favorable": max(movements) if movements else None,
            "max_adverse": min(movements) if movements else None,
        }

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
    def _recommendation_score(
        *,
        hit_rate: float,
        halfway_rate: float,
        adverse_rate: float,
        candidate_count: int,
        base_candidate_count: int,
        average_favorable: float | None,
        average_adverse: float | None,
    ) -> float:
        if not base_candidate_count or not candidate_count:
            return 0.0

        retention = candidate_count / base_candidate_count
        favorable = max(0.0, average_favorable or 0.0)
        adverse = abs(min(0.0, average_adverse or 0.0))
        movement_balance = favorable / (favorable + adverse) if favorable + adverse > 0 else 0.0
        score = (
            hit_rate * 45.0
            + halfway_rate * 20.0
            + (1.0 - adverse_rate) * 20.0
            + retention * 10.0
            + movement_balance * 5.0
        )
        return round(score, 2)

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
