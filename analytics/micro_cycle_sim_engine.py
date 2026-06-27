from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


MICRO_CYCLE_SCENARIOS = (
    "current_mean_reversion",
    "relaxed_entry_30_70",
    "relaxed_entry_40_60",
    "spread_only",
    "short_term_mean_reversion",
)

MICRO_CYCLE_TARGET_PERCENTS = (0.001, 0.0025, 0.005, 0.0075, 0.01)


@dataclass(frozen=True)
class MicroCycleSimulationResult:
    scenario: str
    target_percent: float
    max_holding_seconds: float | None
    total_samples: int
    sample_span_hours: float
    cycles_opened: int
    closed_by_target: int
    closed_by_timeout: int
    still_open_at_end: int
    win_rate: float
    gross_profit: float
    net_profit: float
    average_net_per_cycle: float
    average_holding_seconds: float | None
    median_holding_seconds: float | None
    max_holding_seconds_observed: float | None
    worst_unrealized_loss: float
    skipped_opportunities_due_to_active_cycle: int
    opportunities_used_rate: float
    cycles_per_hour: float
    estimated_cycles_per_day: float
    recommendation_score: float


@dataclass(frozen=True)
class MicroCycleSimulationReport:
    results: list[MicroCycleSimulationResult]
    best_result: MicroCycleSimulationResult | None
    recommendation: str


@dataclass
class _ActiveCycle:
    direction: str
    entry_price: float
    target_price: float
    quantity: float
    opened_at: datetime | None


class MicroCycleSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)
        portfolio_value = config.backtest_initial_usdt + config.backtest_initial_usdc
        self.simulated_notional = max(portfolio_value * config.trade_size_percent, config.min_notional)

    def build_report(
        self,
        *,
        scenario: str | None = None,
        target_percent: float | None = None,
        max_holding_seconds: float | None = None,
    ) -> MicroCycleSimulationReport:
        scenarios = [scenario] if scenario else list(MICRO_CYCLE_SCENARIOS)
        targets = [target_percent] if target_percent is not None else list(MICRO_CYCLE_TARGET_PERCENTS)
        rows = self._load_rows()

        results = [
            self.simulate(
                rows=rows,
                scenario=item_scenario,
                target_percent=item_target,
                max_holding_seconds=max_holding_seconds,
            )
            for item_scenario in scenarios
            for item_target in targets
        ]
        best_result = max(results, key=lambda item: item.recommendation_score, default=None)
        return MicroCycleSimulationReport(
            results=results,
            best_result=best_result,
            recommendation=self._recommend(best_result, rows),
        )

    def simulate(
        self,
        *,
        rows: list[dict],
        scenario: str,
        target_percent: float,
        max_holding_seconds: float | None = None,
    ) -> MicroCycleSimulationResult:
        if scenario not in MICRO_CYCLE_SCENARIOS:
            raise ValueError(f"Unsupported micro-cycle scenario: {scenario}")
        if target_percent <= 0:
            raise ValueError("target_percent must be greater than 0.")
        if max_holding_seconds is not None and max_holding_seconds <= 0:
            raise ValueError("max_holding_seconds must be greater than 0 when provided.")

        active: _ActiveCycle | None = None
        cycles_opened = 0
        closed_by_target = 0
        closed_by_timeout = 0
        skipped_opportunities = 0
        gross_profit = 0.0
        net_profit = 0.0
        wins = 0
        holding_times: list[float] = []
        worst_unrealized_loss = 0.0

        for index, row in enumerate(rows):
            if active is not None:
                if self._direction_for_scenario(row, index, scenario) is not None:
                    skipped_opportunities += 1

                unrealized = self._profit(active, row["price"])
                worst_unrealized_loss = min(worst_unrealized_loss, unrealized.net_profit)

                close_reason = self._close_reason(active, row, max_holding_seconds)
                if close_reason is None:
                    continue

                gross_profit += unrealized.gross_profit
                net_profit += unrealized.net_profit
                if unrealized.net_profit > 0:
                    wins += 1
                holding_times.append(self._holding_seconds(active.opened_at, row["parsed_timestamp"]))
                if close_reason == "target":
                    closed_by_target += 1
                else:
                    closed_by_timeout += 1
                active = None
                continue

            direction = self._direction_for_scenario(row, index, scenario)
            if direction is None:
                continue

            entry_price = row["price"]
            if entry_price <= 0:
                continue
            quantity = self.simulated_notional / entry_price
            target_decimal = target_percent / 100.0
            target_price = (
                entry_price * (1.0 + target_decimal)
                if direction == "BUY"
                else entry_price * (1.0 - target_decimal)
            )
            active = _ActiveCycle(
                direction=direction,
                entry_price=entry_price,
                target_price=target_price,
                quantity=quantity,
                opened_at=row["parsed_timestamp"],
            )
            cycles_opened += 1

        closed_count = closed_by_target + closed_by_timeout
        opportunities = cycles_opened + skipped_opportunities
        span_hours = self._sample_span_hours(rows)
        cycles_per_hour = closed_count / span_hours if span_hours > 0 else 0.0
        win_rate = wins / closed_count if closed_count else 0.0
        recommendation_score = self._score(
            net_profit=net_profit,
            win_rate=win_rate,
            cycles_per_day=cycles_per_hour * 24.0,
            still_open=1 if active else 0,
        )

        return MicroCycleSimulationResult(
            scenario=scenario,
            target_percent=target_percent,
            max_holding_seconds=max_holding_seconds,
            total_samples=len(rows),
            sample_span_hours=span_hours,
            cycles_opened=cycles_opened,
            closed_by_target=closed_by_target,
            closed_by_timeout=closed_by_timeout,
            still_open_at_end=1 if active else 0,
            win_rate=win_rate,
            gross_profit=gross_profit,
            net_profit=net_profit,
            average_net_per_cycle=net_profit / closed_count if closed_count else 0.0,
            average_holding_seconds=sum(holding_times) / len(holding_times) if holding_times else None,
            median_holding_seconds=float(median(holding_times)) if holding_times else None,
            max_holding_seconds_observed=max(holding_times) if holding_times else None,
            worst_unrealized_loss=worst_unrealized_loss,
            skipped_opportunities_due_to_active_cycle=skipped_opportunities,
            opportunities_used_rate=cycles_opened / opportunities if opportunities else 0.0,
            cycles_per_hour=cycles_per_hour,
            estimated_cycles_per_day=cycles_per_hour * 24.0,
            recommendation_score=recommendation_score,
        )

    def _direction_for_scenario(self, row: dict, index: int, scenario: str) -> str | None:
        if self._basic_failures(row):
            return None
        if scenario == "current_mean_reversion":
            direction = self._zone_direction(row, 25.0, 75.0)
            return direction if direction and self._micro_trend_pass(direction, row["micro_trend"]) else None
        if scenario == "relaxed_entry_30_70":
            direction = self._zone_direction(row, 30.0, 70.0)
            return direction if direction and self._micro_trend_pass(direction, row["micro_trend"]) else None
        if scenario == "relaxed_entry_40_60":
            direction = self._zone_direction(row, 40.0, 60.0)
            return direction if direction and self._micro_trend_pass(direction, row["micro_trend"]) else None
        if scenario == "spread_only":
            return "BUY" if row["work_position"] <= 50.0 else "SELL"
        if scenario == "short_term_mean_reversion":
            short_center = row["short_center"]
            if short_center <= 0 or row["price"] == short_center:
                return None
            return "BUY" if row["price"] < short_center else "SELL"
        return None

    def _close_reason(
        self,
        active: _ActiveCycle,
        row: dict,
        max_holding_seconds: float | None,
    ) -> str | None:
        price = row["price"]
        if active.direction == "BUY" and price >= active.target_price:
            return "target"
        if active.direction == "SELL" and price <= active.target_price:
            return "target"
        if max_holding_seconds is None:
            return None
        if self._holding_seconds(active.opened_at, row["parsed_timestamp"]) >= max_holding_seconds:
            return "timeout"
        return None

    def _profit(self, active: _ActiveCycle, close_price: float):
        direction = "BUY_USDC" if active.direction == "BUY" else "SELL_USDC"
        return self.fee_engine.calculate_profit(
            direction=direction,
            open_price=active.entry_price,
            close_price=close_price,
            quantity=active.quantity,
            use_taker_fee=True,
        )

    def _basic_failures(self, row: dict) -> list[str]:
        failures = []
        if not (0.0 < row["spread"] <= self.config.max_allowed_spread):
            failures.append("spread")
        if row["market_regime"] == "ABNORMAL":
            failures.append("market_regime")
        if row["volatility_regime"] == "EXTREME":
            failures.append("volatility_regime")
        return failures

    def _load_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    price,
                    work_position,
                    distance_to_short_center,
                    spread,
                    market_regime,
                    micro_trend,
                    volatility_regime
                FROM market_snapshots_hf
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        for index, row in enumerate(rows):
            (
                timestamp,
                price,
                work_position,
                distance_to_short_center,
                spread,
                market_regime,
                micro_trend,
                volatility_regime,
            ) = row
            current_price = self._float(price)
            result.append({
                "index": index,
                "timestamp": clean_display_text(timestamp),
                "parsed_timestamp": self._parse_timestamp(timestamp),
                "price": current_price,
                "work_position": self._float(work_position),
                "short_center": current_price - self._float(distance_to_short_center),
                "spread": self._float(spread),
                "market_regime": self._text(market_regime),
                "micro_trend": self._text(micro_trend),
                "volatility_regime": self._text(volatility_regime),
            })
        return result

    @staticmethod
    def _zone_direction(row: dict, buy_threshold: float, sell_threshold: float) -> str | None:
        if row["work_position"] <= buy_threshold:
            return "BUY"
        if row["work_position"] >= sell_threshold:
            return "SELL"
        return None

    @staticmethod
    def _micro_trend_pass(direction: str, micro_trend: str) -> bool:
        if direction == "BUY":
            return micro_trend == "BUY_DOMINANT"
        if direction == "SELL":
            return micro_trend == "SELL_DOMINANT"
        return False

    @staticmethod
    def _sample_span_hours(rows: list[dict]) -> float:
        timestamps = [row["parsed_timestamp"] for row in rows if row["parsed_timestamp"] is not None]
        if len(timestamps) >= 2:
            return max((max(timestamps) - min(timestamps)).total_seconds() / 3600.0, 1 / 3600)
        return 0.0

    @staticmethod
    def _holding_seconds(opened_at: datetime | None, closed_at: datetime | None) -> float:
        if opened_at is None or closed_at is None:
            return 0.0
        return max((closed_at - opened_at).total_seconds(), 0.0)

    @staticmethod
    def _score(*, net_profit: float, win_rate: float, cycles_per_day: float, still_open: int) -> float:
        open_penalty = 0.10 if still_open else 0.0
        profit_score = max(min(net_profit * 1000.0, 2.0), -2.0)
        frequency_score = min(cycles_per_day / 500.0, 2.0)
        return profit_score + frequency_score + win_rate - open_penalty

    @staticmethod
    def _recommend(best: MicroCycleSimulationResult | None, rows: list[dict]) -> str:
        if not rows:
            return "NEEDS_MORE_DATA"
        if best is None or best.closed_by_target + best.closed_by_timeout < 5:
            return "NEEDS_MORE_DATA"
        if best.net_profit <= 0 or best.win_rate < 0.40:
            return "NOT_VIABLE"
        if best.estimated_cycles_per_day >= 500 and best.win_rate >= 0.50:
            return "STRONG_CANDIDATE"
        return "PROMISING"

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        try:
            return datetime.fromisoformat(clean_display_text(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
