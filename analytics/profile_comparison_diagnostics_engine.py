from __future__ import annotations

from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.exchange_rules_engine import ExchangeRulesEngine
from trading.fee_rate_provider import FeeRateProvider, FeeRates


DEFAULT_PROFILE_COMPARISON_HORIZONS = (1, 3, 5, 10, 20, 30)


@dataclass(frozen=True)
class ProfileComparisonDefinition:
    name: str
    buy_threshold: float
    sell_threshold: float
    micro_trend_mode: str


PROFILE_COMPARISON_DEFINITIONS = (
    ProfileComparisonDefinition(
        name="mean_reversion_v2",
        buy_threshold=25.0,
        sell_threshold=75.0,
        micro_trend_mode="strict",
    ),
    ProfileComparisonDefinition(
        name="mean_reversion_v3",
        buy_threshold=30.0,
        sell_threshold=70.0,
        micro_trend_mode="strict",
    ),
    ProfileComparisonDefinition(
        name="mean_reversion_v4",
        buy_threshold=25.0,
        sell_threshold=75.0,
        micro_trend_mode="allow_neutral",
    ),
    ProfileComparisonDefinition(
        name="mean_reversion_v5",
        buy_threshold=30.0,
        sell_threshold=70.0,
        micro_trend_mode="allow_neutral",
    ),
)


@dataclass(frozen=True)
class ProfileHorizonHitRate:
    horizon: int
    hit_target_count: int
    hit_rate: float


@dataclass(frozen=True)
class ProfileComparisonResult:
    profile: str
    buy_threshold: float
    sell_threshold: float
    micro_trend_mode: str
    total_samples: int
    candidate_count: int
    buy_count: int
    sell_count: int
    candidate_frequency: float
    target_hit_rates: list[ProfileHorizonHitRate]
    average_favorable_movement: float | None
    average_adverse_movement: float | None
    best_movement: float | None
    worst_movement: float | None
    gross_profit_min: float | None
    gross_profit_max: float | None
    net_profit_min: float | None
    net_profit_max: float | None
    recommendation_score: float


@dataclass(frozen=True)
class ProfileComparisonReport:
    fee_rates: FeeRates
    target_profit: float
    horizons: tuple[int, ...]
    results: list[ProfileComparisonResult]


class ProfileComparisonDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.exchange_rules = ExchangeRulesEngine(config)
        self.fee_rates = FeeRateProvider(config).get_rates()

    def build_report(
        self,
        horizons: tuple[int, ...] = DEFAULT_PROFILE_COMPARISON_HORIZONS,
    ) -> ProfileComparisonReport:
        snapshots = self._load_snapshot_rows()
        return ProfileComparisonReport(
            fee_rates=self.fee_rates,
            target_profit=self.config.target_profit,
            horizons=horizons,
            results=[
                self._evaluate_profile(snapshots, definition, horizons)
                for definition in PROFILE_COMPARISON_DEFINITIONS
            ],
        )

    def _evaluate_profile(
        self,
        snapshots: list[dict],
        definition: ProfileComparisonDefinition,
        horizons: tuple[int, ...],
    ) -> ProfileComparisonResult:
        candidates = [
            (index, snapshot, self._entry_direction(snapshot, definition))
            for index, snapshot in enumerate(snapshots)
            if self._entry_direction(snapshot, definition) in {"BUY_USDC", "SELL_USDC"}
            and index + 1 < len(snapshots)
        ]

        buy_count = sum(1 for _index, _snapshot, direction in candidates if direction == "BUY_USDC")
        sell_count = sum(1 for _index, _snapshot, direction in candidates if direction == "SELL_USDC")

        favorable_movements: list[float] = []
        adverse_movements: list[float] = []
        best_movements: list[float] = []
        worst_movements: list[float] = []
        gross_profits: list[float] = []
        net_profits: list[float] = []

        max_horizon = max(horizons) if horizons else 0
        for index, snapshot, direction in candidates:
            future = snapshots[index + 1 : index + max_horizon + 1]
            movements = [
                self._movement_in_expected_direction(
                    direction,
                    entry_price=snapshot["price"],
                    future_price=future_snapshot["price"],
                )
                for future_snapshot in future
            ]
            if movements:
                best = max(movements)
                worst = min(movements)
                best_movements.append(best)
                worst_movements.append(worst)
                favorable_movements.append(max(0.0, best))
                adverse_movements.append(min(0.0, worst))

            target_price = self._target_price(direction, snapshot["price"])
            risk = self._risk_result(direction, snapshot["price"], target_price)
            gross_profits.append(risk.gross_profit)
            net_profits.append(risk.net_profit)

        target_hit_rates = [
            self._evaluate_horizon(candidates, snapshots, horizon)
            for horizon in horizons
        ]

        return ProfileComparisonResult(
            profile=definition.name,
            buy_threshold=definition.buy_threshold,
            sell_threshold=definition.sell_threshold,
            micro_trend_mode=definition.micro_trend_mode,
            total_samples=len(snapshots),
            candidate_count=len(candidates),
            buy_count=buy_count,
            sell_count=sell_count,
            candidate_frequency=len(candidates) / len(snapshots) if snapshots else 0.0,
            target_hit_rates=target_hit_rates,
            average_favorable_movement=self._average(favorable_movements),
            average_adverse_movement=self._average(adverse_movements),
            best_movement=max(best_movements) if best_movements else None,
            worst_movement=min(worst_movements) if worst_movements else None,
            gross_profit_min=min(gross_profits) if gross_profits else None,
            gross_profit_max=max(gross_profits) if gross_profits else None,
            net_profit_min=min(net_profits) if net_profits else None,
            net_profit_max=max(net_profits) if net_profits else None,
            recommendation_score=self._recommendation_score(
                len(candidates),
                len(snapshots),
                target_hit_rates,
                self._average(favorable_movements),
                self._average(adverse_movements),
            ),
        )

    def _evaluate_horizon(
        self,
        candidates: list[tuple[int, dict, str]],
        snapshots: list[dict],
        horizon: int,
    ) -> ProfileHorizonHitRate:
        evaluated = 0
        hit_count = 0
        for index, snapshot, direction in candidates:
            future = snapshots[index + 1 : index + horizon + 1]
            if not future:
                continue

            evaluated += 1
            target_price = self._target_price(direction, snapshot["price"])
            if any(
                self._target_hit(direction, future_snapshot["price"], target_price)
                for future_snapshot in future
            ):
                hit_count += 1

        return ProfileHorizonHitRate(
            horizon=horizon,
            hit_target_count=hit_count,
            hit_rate=hit_count / evaluated if evaluated else 0.0,
        )

    def _entry_direction(self, row: dict, definition: ProfileComparisonDefinition) -> str:
        if not (0.0 < row["spread"] <= self.config.max_allowed_spread):
            return "WAIT"
        if (
            row["market_health_score"] < self.config.min_market_health_score
            or row["market_health_status"] == "UNHEALTHY"
        ):
            return "WAIT"
        if row["market_regime"] == "ABNORMAL" or row["volatility_regime"] == "EXTREME":
            return "WAIT"

        if (
            row["work_position"] <= definition.buy_threshold
            and self._micro_trend_pass("BUY", row["micro_trend"], definition.micro_trend_mode)
        ):
            return "BUY_USDC"
        if (
            row["work_position"] >= definition.sell_threshold
            and self._micro_trend_pass("SELL", row["micro_trend"], definition.micro_trend_mode)
        ):
            return "SELL_USDC"
        return "WAIT"

    @staticmethod
    def _micro_trend_pass(zone: str, micro_trend: str, mode: str) -> bool:
        if mode == "allow_neutral" and micro_trend == "NEUTRAL":
            return True
        if zone == "BUY":
            return micro_trend == "BUY_DOMINANT"
        return micro_trend == "SELL_DOMINANT"

    def _risk_result(self, direction: str, open_price: float, close_price: float):
        budget_total = self.config.backtest_initial_usdt + self.config.backtest_initial_usdc * open_price
        trade_size = budget_total * self.config.trade_size_percent
        return self.exchange_rules.check_profitability_after_rounding(
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            budget_value=trade_size,
        )

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
        candidate_count: int,
        total_samples: int,
        target_hit_rates: list[ProfileHorizonHitRate],
        average_favorable_movement: float | None,
        average_adverse_movement: float | None,
    ) -> float:
        if not total_samples or not candidate_count:
            return 0.0

        hit_rate_30 = target_hit_rates[-1].hit_rate if target_hit_rates else 0.0
        frequency = candidate_count / total_samples
        favorable = max(0.0, average_favorable_movement or 0.0)
        adverse = abs(min(0.0, average_adverse_movement or 0.0))
        movement_balance = favorable / (favorable + adverse) if favorable + adverse > 0 else 0.0

        # Keep the score intentionally simple and bounded. It is a ranking aid,
        # not a strategy decision.
        score = (hit_rate_30 * 70.0) + (min(frequency, 0.5) / 0.5 * 15.0) + (movement_balance * 15.0)
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
