from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.exchange_rules_engine import ExchangeRulesEngine
from trading.fee_rate_provider import FeeRateProvider, FeeRates


DEFAULT_THRESHOLD_VARIANTS = (
    (20.0, 80.0),
    (25.0, 75.0),
    (30.0, 70.0),
    (35.0, 65.0),
    (40.0, 60.0),
)

MICRO_TREND_MODES = ("strict", "allow_neutral", "ignore_micro_trend")
SUPPORTED_SENSITIVITY_PROFILES = ("mean_reversion_v1",)


@dataclass(frozen=True)
class MicroTrendSensitivityResult:
    mode: str
    buy_threshold: float
    sell_threshold: float
    total_samples: int
    zone_count: int
    candidates_count: int
    candidate_frequency: float
    risk_profitability_pass_count: int
    gross_profit_min: float | None
    gross_profit_max: float | None
    net_profit_min: float | None
    net_profit_max: float | None
    micro_trend_distribution: list[tuple[str, int]]
    remaining_blockers: list[tuple[str, int]]


@dataclass(frozen=True)
class MicroTrendRecommendation:
    mode: str
    buy_threshold: float
    sell_threshold: float
    candidates_count: int
    candidate_frequency: float
    reason: str


@dataclass(frozen=True)
class MicroTrendSensitivityReport:
    profile: str
    fee_rates: FeeRates
    results: list[MicroTrendSensitivityResult]
    recommendation: MicroTrendRecommendation | None


class MicroTrendSensitivityEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.exchange_rules = ExchangeRulesEngine(config)
        self.fee_rates = FeeRateProvider(config).get_rates()

    def build_report(
        self,
        profile: str = "mean_reversion_v1",
        variants: tuple[tuple[float, float], ...] = DEFAULT_THRESHOLD_VARIANTS,
    ) -> MicroTrendSensitivityReport:
        if profile not in SUPPORTED_SENSITIVITY_PROFILES:
            supported = ", ".join(SUPPORTED_SENSITIVITY_PROFILES)
            raise ValueError(f"Unsupported sensitivity profile: {profile}. Supported: {supported}")

        rows = self._load_snapshot_rows()
        results = [
            self._evaluate(rows, mode, buy_threshold, sell_threshold)
            for buy_threshold, sell_threshold in variants
            for mode in MICRO_TREND_MODES
        ]
        return MicroTrendSensitivityReport(
            profile=profile,
            fee_rates=self.fee_rates,
            results=results,
            recommendation=self._recommend(results),
        )

    def _evaluate(
        self,
        rows: list[dict],
        mode: str,
        buy_threshold: float,
        sell_threshold: float,
    ) -> MicroTrendSensitivityResult:
        zone_rows = [
            {
                **row,
                "zone": "BUY" if row["work_position"] <= buy_threshold else "SELL",
            }
            for row in rows
            if row["work_position"] <= buy_threshold or row["work_position"] >= sell_threshold
        ]

        distribution = Counter(row["micro_trend"] for row in zone_rows)
        blockers: Counter[str] = Counter()
        gross_profits: list[float] = []
        net_profits: list[float] = []
        candidates_count = 0
        risk_pass_count = 0

        for row in zone_rows:
            failures = self._basic_failures(row)
            if not self._micro_trend_pass(row["zone"], row["micro_trend"], mode):
                failures.append("micro_trend")

            if failures:
                blockers.update(failures)
                continue

            action = "BUY_USDC" if row["zone"] == "BUY" else "SELL_USDC"
            candidates_count += 1
            risk = self._risk_result(action, row["price"])
            if risk.allowed:
                risk_pass_count += 1
                gross_profits.append(risk.gross_profit)
                net_profits.append(risk.net_profit)
            else:
                blockers.update(["risk_profitability"])

        return MicroTrendSensitivityResult(
            mode=mode,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            total_samples=len(rows),
            zone_count=len(zone_rows),
            candidates_count=candidates_count,
            candidate_frequency=candidates_count / len(rows) if rows else 0.0,
            risk_profitability_pass_count=risk_pass_count,
            gross_profit_min=min(gross_profits) if gross_profits else None,
            gross_profit_max=max(gross_profits) if gross_profits else None,
            net_profit_min=min(net_profits) if net_profits else None,
            net_profit_max=max(net_profits) if net_profits else None,
            micro_trend_distribution=sorted(distribution.items(), key=lambda item: (-item[1], item[0])),
            remaining_blockers=sorted(blockers.items(), key=lambda item: (-item[1], item[0])),
        )

    def _basic_failures(self, row: dict) -> list[str]:
        failures = []
        if not (0.0 < row["spread"] <= self.config.max_allowed_spread):
            failures.append("spread")
        if (
            row["market_health_score"] < self.config.min_market_health_score
            or row["market_health_status"] == "UNHEALTHY"
        ):
            failures.append("market_health")
        if row["market_regime"] == "ABNORMAL":
            failures.append("market_regime")
        if row["volatility_regime"] == "EXTREME":
            failures.append("volatility_regime")
        return failures

    def _risk_result(self, action: str, price: float):
        target_price = price * (1 + self.config.target_profit)
        if action == "SELL_USDC":
            target_price = price * (1 - self.config.target_profit)

        budget_total = self.config.backtest_initial_usdt + self.config.backtest_initial_usdc * price
        trade_size = budget_total * self.config.trade_size_percent
        return self.exchange_rules.check_profitability_after_rounding(
            direction=action,
            open_price=price,
            close_price=target_price,
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

    @staticmethod
    def _micro_trend_pass(zone: str, micro_trend: str, mode: str) -> bool:
        if mode == "ignore_micro_trend":
            return True
        if mode == "allow_neutral" and micro_trend == "NEUTRAL":
            return True
        if zone == "BUY":
            return micro_trend == "BUY_DOMINANT"
        return micro_trend == "SELL_DOMINANT"

    @staticmethod
    def _recommend(results: list[MicroTrendSensitivityResult]) -> MicroTrendRecommendation | None:
        viable = [
            result
            for result in results
            if result.candidates_count > 0
            and result.risk_profitability_pass_count == result.candidates_count
        ]
        if not viable:
            return None

        mode_rank = {"strict": 0, "allow_neutral": 1, "ignore_micro_trend": 2}
        viable.sort(
            key=lambda result: (
                mode_rank[result.mode],
                abs(result.candidate_frequency - 0.5),
                result.buy_threshold,
            )
        )
        selected = viable[0]
        return MicroTrendRecommendation(
            mode=selected.mode,
            buy_threshold=selected.buy_threshold,
            sell_threshold=selected.sell_threshold,
            candidates_count=selected.candidates_count,
            candidate_frequency=selected.candidate_frequency,
            reason=(
                "Lowest-relaxation combo with positive candidates and all candidate "
                "profitability checks passing."
            ),
        )

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
