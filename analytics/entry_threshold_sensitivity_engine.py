from __future__ import annotations

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

SUPPORTED_SENSITIVITY_PROFILES = ("mean_reversion_v1",)


@dataclass(frozen=True)
class EntryThresholdVariantResult:
    buy_threshold: float
    sell_threshold: float
    total_samples: int
    buy_zone_count: int
    sell_zone_count: int
    candidate_count: int
    micro_trend_pass_count: int
    risk_profitability_pass_count: int
    min_notional_pass_count: int
    gross_profit_min: float | None
    gross_profit_max: float | None
    net_profit_min: float | None
    net_profit_max: float | None
    expected_trade_frequency: float
    remaining_blockers: list[tuple[str, int]]


@dataclass(frozen=True)
class EntryThresholdSensitivityReport:
    profile: str
    configured_buy_threshold: float
    configured_sell_threshold: float
    fee_rates: FeeRates
    variants: list[EntryThresholdVariantResult]


class EntryThresholdSensitivityEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.exchange_rules = ExchangeRulesEngine(config)
        self.fee_rates = FeeRateProvider(config).get_rates()

    def build_report(
        self,
        profile: str = "mean_reversion_v1",
        variants: tuple[tuple[float, float], ...] = DEFAULT_THRESHOLD_VARIANTS,
    ) -> EntryThresholdSensitivityReport:
        if profile not in SUPPORTED_SENSITIVITY_PROFILES:
            supported = ", ".join(SUPPORTED_SENSITIVITY_PROFILES)
            raise ValueError(f"Unsupported sensitivity profile: {profile}. Supported: {supported}")

        rows = self._load_snapshot_rows()
        return EntryThresholdSensitivityReport(
            profile=profile,
            configured_buy_threshold=self.config.buy_zone_max,
            configured_sell_threshold=self.config.sell_zone_min,
            fee_rates=self.fee_rates,
            variants=[self._evaluate_variant(rows, buy, sell) for buy, sell in variants],
        )

    def _evaluate_variant(
        self,
        rows: list[dict],
        buy_threshold: float,
        sell_threshold: float,
    ) -> EntryThresholdVariantResult:
        buy_rows = [row for row in rows if row["work_position"] <= buy_threshold]
        sell_rows = [row for row in rows if row["work_position"] >= sell_threshold]
        zone_rows = [*buy_rows, *sell_rows]

        candidate_rows = []
        micro_trend_pass_count = 0
        risk_pass_count = 0
        min_notional_pass_count = 0
        gross_profits: list[float] = []
        net_profits: list[float] = []
        blockers: dict[str, int] = {}

        for row in zone_rows:
            zone = "BUY" if row["work_position"] <= buy_threshold else "SELL"
            failures = self._basic_failures(row)
            micro_trend_pass = self._micro_trend_pass(zone, row["micro_trend"])
            if micro_trend_pass is True:
                micro_trend_pass_count += 1
            else:
                failures.append("micro_trend")

            if failures:
                for failure in failures:
                    blockers[failure] = blockers.get(failure, 0) + 1
                continue

            action = "BUY_USDC" if zone == "BUY" else "SELL_USDC"
            risk = self._risk_result(action, row["price"])
            if (
                risk.open_order.notional >= self.config.min_notional
                and risk.close_order.notional >= self.config.min_notional
            ):
                min_notional_pass_count += 1
            if risk.allowed:
                risk_pass_count += 1
                candidate_rows.append(row)
                gross_profits.append(risk.gross_profit)
                net_profits.append(risk.net_profit)
            else:
                blockers["risk_profitability"] = blockers.get("risk_profitability", 0) + 1
                if (
                    risk.open_order.notional < self.config.min_notional
                    or risk.close_order.notional < self.config.min_notional
                ):
                    blockers["min_notional_or_order_sizing"] = blockers.get("min_notional_or_order_sizing", 0) + 1

        return EntryThresholdVariantResult(
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            total_samples=len(rows),
            buy_zone_count=len(buy_rows),
            sell_zone_count=len(sell_rows),
            candidate_count=len(candidate_rows),
            micro_trend_pass_count=micro_trend_pass_count,
            risk_profitability_pass_count=risk_pass_count,
            min_notional_pass_count=min_notional_pass_count,
            gross_profit_min=min(gross_profits) if gross_profits else None,
            gross_profit_max=max(gross_profits) if gross_profits else None,
            net_profit_min=min(net_profits) if net_profits else None,
            net_profit_max=max(net_profits) if net_profits else None,
            expected_trade_frequency=len(candidate_rows) / len(rows) if rows else 0.0,
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
