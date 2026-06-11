from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


SUPPORTED_HOLDING_HORIZON_PROFILES = ("mean_reversion_v1", "mean_reversion_v2")
DEFAULT_HOLDING_HORIZONS = (1, 3, 5, 10, 20, 30)


@dataclass(frozen=True)
class HoldingHorizonResult:
    horizon: int
    candidates_count: int
    hit_target_count: int
    hit_rate: float
    average_time_to_target: float | None
    max_adverse_movement: float | None
    average_adverse_movement: float | None
    expired_without_target_count: int


@dataclass(frozen=True)
class OpenCycleHoldingDiagnostic:
    db_id: int
    cycle_id: int
    profile: str
    direction: str
    opened_at: str
    age_seconds: float
    open_price: float
    target_price: float
    current_price: float
    distance_to_target: float
    max_observed_favorable_movement: float | None
    max_observed_adverse_movement: float | None


@dataclass(frozen=True)
class HoldingHorizonDiagnosticsReport:
    profile: str
    target_profit: float
    current_price: float
    horizons: list[HoldingHorizonResult]
    open_cycles: list[OpenCycleHoldingDiagnostic]


class HoldingHorizonDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(
        self,
        *,
        current_price: float,
        profile: str = "mean_reversion_v2",
        horizons: tuple[int, ...] = DEFAULT_HOLDING_HORIZONS,
    ) -> HoldingHorizonDiagnosticsReport:
        if profile not in SUPPORTED_HOLDING_HORIZON_PROFILES:
            supported = ", ".join(SUPPORTED_HOLDING_HORIZON_PROFILES)
            raise ValueError(f"Unsupported holding horizon profile: {profile}. Supported: {supported}")

        snapshots = self._load_snapshot_rows()
        return HoldingHorizonDiagnosticsReport(
            profile=profile,
            target_profit=self.config.target_profit,
            current_price=current_price,
            horizons=[
                self._evaluate_horizon(snapshots, profile, horizon)
                for horizon in horizons
            ],
            open_cycles=self._build_open_cycle_diagnostics(snapshots, current_price, profile),
        )

    def _evaluate_horizon(
        self,
        snapshots: list[dict],
        profile: str,
        horizon: int,
    ) -> HoldingHorizonResult:
        candidates = [
            (index, snapshot, self._entry_direction(snapshot, profile))
            for index, snapshot in enumerate(snapshots)
            if self._entry_direction(snapshot, profile) in {"BUY_USDC", "SELL_USDC"}
            and index + 1 < len(snapshots)
        ]

        evaluated = 0
        hit_count = 0
        time_to_target_values: list[int] = []
        adverse_movements: list[float] = []

        for index, snapshot, direction in candidates:
            future = snapshots[index + 1 : index + horizon + 1]
            if not future:
                continue

            evaluated += 1
            target_price = self._target_price(direction, snapshot["price"])
            hit_step = None
            worst_adverse = 0.0

            for step, future_snapshot in enumerate(future, start=1):
                movement = self._movement_in_expected_direction(
                    direction,
                    entry_price=snapshot["price"],
                    future_price=future_snapshot["price"],
                )
                worst_adverse = min(worst_adverse, movement)

                if self._target_hit(direction, future_snapshot["price"], target_price):
                    hit_step = step
                    break

            adverse_movements.append(worst_adverse)
            if hit_step is not None:
                hit_count += 1
                time_to_target_values.append(hit_step)

        return HoldingHorizonResult(
            horizon=horizon,
            candidates_count=evaluated,
            hit_target_count=hit_count,
            hit_rate=hit_count / evaluated if evaluated else 0.0,
            average_time_to_target=(
                sum(time_to_target_values) / len(time_to_target_values)
                if time_to_target_values
                else None
            ),
            max_adverse_movement=min(adverse_movements) if adverse_movements else None,
            average_adverse_movement=(
                sum(adverse_movements) / len(adverse_movements)
                if adverse_movements
                else None
            ),
            expired_without_target_count=evaluated - hit_count,
        )

    def _build_open_cycle_diagnostics(
        self,
        snapshots: list[dict],
        current_price: float,
        profile: str,
    ) -> list[OpenCycleHoldingDiagnostic]:
        rows = self.database.load_open_paper_cycles(limit=1000)
        diagnostics: list[OpenCycleHoldingDiagnostic] = []
        for row in rows:
            (
                db_id,
                _timestamp,
                cycle_id,
                strategy_profile,
                direction,
                _status,
                open_price,
                close_price,
                _quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                _net_profit,
                opened_at,
                _closed_at,
            ) = row
            strategy_profile = clean_display_text(strategy_profile or "UNKNOWN")
            if strategy_profile != profile:
                continue

            direction = clean_display_text(direction)
            open_price = float(open_price)
            target_price = float(close_price)
            opened_at_text = clean_display_text(opened_at)
            observed_movements = [
                self._movement_in_expected_direction(direction, open_price, snapshot["price"])
                for snapshot in snapshots
                if snapshot["timestamp"] >= opened_at_text
            ]

            diagnostics.append(
                OpenCycleHoldingDiagnostic(
                    db_id=int(db_id),
                    cycle_id=int(cycle_id),
                    profile=strategy_profile,
                    direction=direction,
                    opened_at=opened_at_text,
                    age_seconds=self._age_seconds(opened_at_text),
                    open_price=open_price,
                    target_price=target_price,
                    current_price=current_price,
                    distance_to_target=self._distance_to_target(direction, current_price, target_price),
                    max_observed_favorable_movement=(
                        max(observed_movements) if observed_movements else None
                    ),
                    max_observed_adverse_movement=(
                        min(observed_movements) if observed_movements else None
                    ),
                )
            )
        return diagnostics

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

    def _target_price(self, direction: str, entry_price: float) -> float:
        if direction == "BUY_USDC":
            return entry_price * (1 + self.config.target_profit)
        return entry_price * (1 - self.config.target_profit)

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
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _age_seconds(opened_at: str) -> float:
        opened_at_dt = datetime.fromisoformat(opened_at)
        now = datetime.now(tz=opened_at_dt.tzinfo) if opened_at_dt.tzinfo else datetime.now()
        return max(0.0, (now - opened_at_dt).total_seconds())

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
