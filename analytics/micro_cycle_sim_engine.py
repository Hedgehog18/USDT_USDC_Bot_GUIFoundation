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
    target_net_profit: float
    target_win_rate: float
    target_avg_net: float
    target_best_profit: float
    target_worst_loss: float
    timeout_net_profit: float
    timeout_win_rate: float
    timeout_avg_net: float
    timeout_best_profit: float
    timeout_worst_loss: float
    timeout_profit_count: int
    timeout_loss_count: int
    max_consecutive_losses: int
    max_consecutive_timeout_losses: int
    max_drawdown_by_realized_equity: float
    worst_realized_cycle: float
    best_realized_cycle: float
    positive_cycles_count: int
    negative_cycles_count: int
    breakeven_cycles_count: int
    profit_share_from_top_1_cycle: float
    profit_share_from_top_3_cycles: float
    profit_share_from_top_5_cycles: float
    cycles: list["MicroCycleClosedCycle"]


@dataclass(frozen=True)
class MicroCycleSimulationReport:
    results: list[MicroCycleSimulationResult]
    best_result: MicroCycleSimulationResult | None
    recommendation: str


@dataclass(frozen=True)
class MicroCycleClosedCycle:
    opened_at: str
    closed_at: str
    direction: str
    entry_price: float
    exit_price: float
    close_reason: str
    holding_seconds: float
    gross_profit: float
    net_profit: float
    max_unrealized_loss: float


@dataclass
class _ActiveCycle:
    direction: str
    entry_price: float
    target_price: float
    quantity: float
    opened_at: datetime | None
    max_unrealized_loss: float = 0.0


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
        skipped_opportunities = 0
        worst_unrealized_loss = 0.0
        closed_cycles: list[MicroCycleClosedCycle] = []

        for index, row in enumerate(rows):
            if active is not None:
                if self._direction_for_scenario(row, index, scenario) is not None:
                    skipped_opportunities += 1

                unrealized = self._profit(active, row["price"])
                worst_unrealized_loss = min(worst_unrealized_loss, unrealized.net_profit)
                active.max_unrealized_loss = min(active.max_unrealized_loss, unrealized.net_profit)

                close_reason = self._close_reason(active, row, max_holding_seconds)
                if close_reason is None:
                    continue

                closed_cycles.append(self._closed_cycle(active, row, close_reason, unrealized))
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

        closed_by_target = sum(1 for cycle in closed_cycles if cycle.close_reason == "target")
        closed_by_timeout = sum(1 for cycle in closed_cycles if cycle.close_reason == "timeout")
        closed_count = closed_by_target + closed_by_timeout
        gross_profit = sum(cycle.gross_profit for cycle in closed_cycles)
        net_profit = sum(cycle.net_profit for cycle in closed_cycles)
        wins = sum(1 for cycle in closed_cycles if cycle.net_profit > 0)
        holding_times = [cycle.holding_seconds for cycle in closed_cycles]
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
            target_net_profit=self._net_profit_for(closed_cycles, "target"),
            target_win_rate=self._win_rate_for(closed_cycles, "target"),
            target_avg_net=self._avg_net_for(closed_cycles, "target"),
            target_best_profit=self._best_profit_for(closed_cycles, "target"),
            target_worst_loss=self._worst_loss_for(closed_cycles, "target"),
            timeout_net_profit=self._net_profit_for(closed_cycles, "timeout"),
            timeout_win_rate=self._win_rate_for(closed_cycles, "timeout"),
            timeout_avg_net=self._avg_net_for(closed_cycles, "timeout"),
            timeout_best_profit=self._best_profit_for(closed_cycles, "timeout"),
            timeout_worst_loss=self._worst_loss_for(closed_cycles, "timeout"),
            timeout_profit_count=sum(
                1 for cycle in closed_cycles if cycle.close_reason == "timeout" and cycle.net_profit > 0
            ),
            timeout_loss_count=sum(
                1 for cycle in closed_cycles if cycle.close_reason == "timeout" and cycle.net_profit < 0
            ),
            max_consecutive_losses=self._max_consecutive_losses(closed_cycles),
            max_consecutive_timeout_losses=self._max_consecutive_timeout_losses(closed_cycles),
            max_drawdown_by_realized_equity=self._max_drawdown(closed_cycles),
            worst_realized_cycle=min((cycle.net_profit for cycle in closed_cycles), default=0.0),
            best_realized_cycle=max((cycle.net_profit for cycle in closed_cycles), default=0.0),
            positive_cycles_count=sum(1 for cycle in closed_cycles if cycle.net_profit > 0),
            negative_cycles_count=sum(1 for cycle in closed_cycles if cycle.net_profit < 0),
            breakeven_cycles_count=sum(1 for cycle in closed_cycles if cycle.net_profit == 0),
            profit_share_from_top_1_cycle=self._profit_share(closed_cycles, 1),
            profit_share_from_top_3_cycles=self._profit_share(closed_cycles, 3),
            profit_share_from_top_5_cycles=self._profit_share(closed_cycles, 5),
            cycles=closed_cycles,
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

    def _closed_cycle(self, active: _ActiveCycle, row: dict, close_reason: str, profit) -> MicroCycleClosedCycle:
        return MicroCycleClosedCycle(
            opened_at=active.opened_at.isoformat() if active.opened_at else "",
            closed_at=row["parsed_timestamp"].isoformat() if row["parsed_timestamp"] else "",
            direction=active.direction,
            entry_price=active.entry_price,
            exit_price=row["price"],
            close_reason=close_reason,
            holding_seconds=self._holding_seconds(active.opened_at, row["parsed_timestamp"]),
            gross_profit=profit.gross_profit,
            net_profit=profit.net_profit,
            max_unrealized_loss=active.max_unrealized_loss,
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

    @staticmethod
    def _cycles_for_reason(
        cycles: list[MicroCycleClosedCycle],
        reason: str,
    ) -> list[MicroCycleClosedCycle]:
        return [cycle for cycle in cycles if cycle.close_reason == reason]

    def _net_profit_for(self, cycles: list[MicroCycleClosedCycle], reason: str) -> float:
        return sum(cycle.net_profit for cycle in self._cycles_for_reason(cycles, reason))

    def _win_rate_for(self, cycles: list[MicroCycleClosedCycle], reason: str) -> float:
        items = self._cycles_for_reason(cycles, reason)
        return sum(1 for cycle in items if cycle.net_profit > 0) / len(items) if items else 0.0

    def _avg_net_for(self, cycles: list[MicroCycleClosedCycle], reason: str) -> float:
        items = self._cycles_for_reason(cycles, reason)
        return sum(cycle.net_profit for cycle in items) / len(items) if items else 0.0

    def _best_profit_for(self, cycles: list[MicroCycleClosedCycle], reason: str) -> float:
        items = self._cycles_for_reason(cycles, reason)
        return max((cycle.net_profit for cycle in items), default=0.0)

    def _worst_loss_for(self, cycles: list[MicroCycleClosedCycle], reason: str) -> float:
        items = self._cycles_for_reason(cycles, reason)
        return min((cycle.net_profit for cycle in items), default=0.0)

    @staticmethod
    def _max_consecutive_losses(cycles: list[MicroCycleClosedCycle]) -> int:
        max_streak = 0
        current = 0
        for cycle in cycles:
            if cycle.net_profit < 0:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    @staticmethod
    def _max_consecutive_timeout_losses(cycles: list[MicroCycleClosedCycle]) -> int:
        max_streak = 0
        current = 0
        for cycle in cycles:
            if cycle.close_reason == "timeout" and cycle.net_profit < 0:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    @staticmethod
    def _max_drawdown(cycles: list[MicroCycleClosedCycle]) -> float:
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for cycle in cycles:
            equity += cycle.net_profit
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return max_drawdown

    @staticmethod
    def _profit_share(cycles: list[MicroCycleClosedCycle], top_count: int) -> float:
        positive_profits = sorted((cycle.net_profit for cycle in cycles if cycle.net_profit > 0), reverse=True)
        total_positive_profit = sum(positive_profits)
        if total_positive_profit <= 0:
            return 0.0
        return sum(positive_profits[:top_count]) / total_positive_profit

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
                    volatility_regime,
                    session
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
                session,
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
                "session": self._text(session),
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
