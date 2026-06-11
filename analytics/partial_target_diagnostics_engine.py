from __future__ import annotations

from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.exchange_rules_engine import ExchangeRulesEngine
from trading.fee_rate_provider import FeeRateProvider, FeeRates


PARTIAL_TARGET_MULTIPLIERS = (0.25, 0.50, 0.75, 1.00)
SUPPORTED_PARTIAL_TARGET_PROFILES = ("mean_reversion_v1", "mean_reversion_v2")
DEFAULT_PARTIAL_TARGET_HORIZON = 30


@dataclass(frozen=True)
class PartialTargetResult:
    multiplier: float
    candidate_count: int
    hit_count: int
    hit_rate: float
    estimated_gross_profit_min: float | None
    estimated_gross_profit_max: float | None
    estimated_net_profit_min: float | None
    estimated_net_profit_max: float | None
    average_time_to_target: float | None
    max_adverse_movement_before_hit: float | None
    missed_failed_count: int
    recommendation_score: float


@dataclass(frozen=True)
class PartialTargetDiagnosticsReport:
    profile: str
    base_target_profit: float
    horizon: int
    fee_rates: FeeRates
    results: list[PartialTargetResult]
    fifty_percent_target_better: bool
    seventy_five_percent_target_acceptable: bool


class PartialTargetDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.exchange_rules = ExchangeRulesEngine(config)
        self.fee_rates = FeeRateProvider(config).get_rates()

    def build_report(
        self,
        *,
        profile: str = "mean_reversion_v2",
        horizon: int = DEFAULT_PARTIAL_TARGET_HORIZON,
    ) -> PartialTargetDiagnosticsReport:
        if profile not in SUPPORTED_PARTIAL_TARGET_PROFILES:
            supported = ", ".join(SUPPORTED_PARTIAL_TARGET_PROFILES)
            raise ValueError(f"Unsupported partial target profile: {profile}. Supported: {supported}")

        snapshots = self._load_snapshot_rows()
        candidates = [
            (index, snapshot, self._entry_direction(snapshot, profile))
            for index, snapshot in enumerate(snapshots)
            for direction in [self._entry_direction(snapshot, profile)]
            if direction in {"BUY_USDC", "SELL_USDC"} and index + 1 < len(snapshots)
        ]
        results = [
            self._evaluate_multiplier(snapshots, candidates, multiplier, horizon)
            for multiplier in PARTIAL_TARGET_MULTIPLIERS
        ]

        by_multiplier = {item.multiplier: item for item in results}
        full = by_multiplier[1.00]
        half = by_multiplier[0.50]
        three_quarters = by_multiplier[0.75]

        return PartialTargetDiagnosticsReport(
            profile=profile,
            base_target_profit=self.config.target_profit,
            horizon=horizon,
            fee_rates=self.fee_rates,
            results=results,
            fifty_percent_target_better=half.hit_rate >= full.hit_rate + 0.10,
            seventy_five_percent_target_acceptable=(
                three_quarters.hit_rate >= full.hit_rate
                and three_quarters.recommendation_score >= full.recommendation_score * 0.9
            ),
        )

    def _evaluate_multiplier(
        self,
        snapshots: list[dict],
        candidates: list[tuple[int, dict, str]],
        multiplier: float,
        horizon: int,
    ) -> PartialTargetResult:
        hit_count = 0
        time_to_target: list[int] = []
        adverse_before_hit: list[float] = []
        gross_profits: list[float] = []
        net_profits: list[float] = []

        for index, snapshot, direction in candidates:
            entry_price = snapshot["price"]
            target_price = self._target_price(direction, entry_price, multiplier)
            future = snapshots[index + 1 : index + horizon + 1]
            worst_adverse = 0.0
            hit_step = None

            for step, future_snapshot in enumerate(future, start=1):
                movement = self._movement_in_expected_direction(
                    direction,
                    entry_price=entry_price,
                    future_price=future_snapshot["price"],
                )
                worst_adverse = min(worst_adverse, movement)
                if self._target_hit(direction, future_snapshot["price"], target_price):
                    hit_step = step
                    break

            if hit_step is not None:
                hit_count += 1
                time_to_target.append(hit_step)
                adverse_before_hit.append(worst_adverse)
                risk = self._risk_result(direction, entry_price, target_price)
                gross_profits.append(risk.gross_profit)
                net_profits.append(risk.net_profit)

        candidate_count = len(candidates)
        hit_rate = hit_count / candidate_count if candidate_count else 0.0
        return PartialTargetResult(
            multiplier=multiplier,
            candidate_count=candidate_count,
            hit_count=hit_count,
            hit_rate=hit_rate,
            estimated_gross_profit_min=min(gross_profits) if gross_profits else None,
            estimated_gross_profit_max=max(gross_profits) if gross_profits else None,
            estimated_net_profit_min=min(net_profits) if net_profits else None,
            estimated_net_profit_max=max(net_profits) if net_profits else None,
            average_time_to_target=self._average(time_to_target),
            max_adverse_movement_before_hit=(
                min(adverse_before_hit) if adverse_before_hit else None
            ),
            missed_failed_count=candidate_count - hit_count,
            recommendation_score=self._recommendation_score(
                hit_rate=hit_rate,
                multiplier=multiplier,
                average_time_to_target=self._average(time_to_target),
                net_profit_max=max(net_profits) if net_profits else None,
            ),
        )

    def _risk_result(self, direction: str, open_price: float, close_price: float):
        budget_total = self.config.backtest_initial_usdt + self.config.backtest_initial_usdc * open_price
        trade_size = budget_total * self.config.trade_size_percent
        return self.exchange_rules.check_profitability_after_rounding(
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            budget_value=trade_size,
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

    def _target_price(self, direction: str, entry_price: float, multiplier: float) -> float:
        target_profit = self.config.target_profit * multiplier
        if direction == "BUY_USDC":
            return entry_price * (1 + target_profit)
        return entry_price * (1 - target_profit)

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
        multiplier: float,
        average_time_to_target: float | None,
        net_profit_max: float | None,
    ) -> float:
        if hit_rate <= 0.0 or net_profit_max is None:
            return 0.0

        time_penalty = min((average_time_to_target or DEFAULT_PARTIAL_TARGET_HORIZON) / 30.0, 1.0)
        score = (hit_rate * 70.0) + (multiplier * 20.0) + ((1.0 - time_penalty) * 10.0)
        return round(score, 2)

    @staticmethod
    def _average(values: list[float | int]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
