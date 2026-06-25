from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


@dataclass(frozen=True)
class ExitOptimizerScenario:
    name: str
    max_holding_seconds: int | None = None
    stop_loss_percent: float | None = None


EXIT_OPTIMIZER_SCENARIOS = (
    ExitOptimizerScenario("no_exit_rule"),
    ExitOptimizerScenario("max_holding_4h", max_holding_seconds=4 * 60 * 60),
    ExitOptimizerScenario("max_holding_8h", max_holding_seconds=8 * 60 * 60),
    ExitOptimizerScenario("max_holding_12h", max_holding_seconds=12 * 60 * 60),
    ExitOptimizerScenario("max_holding_24h", max_holding_seconds=24 * 60 * 60),
    ExitOptimizerScenario("stop_loss_0.02%", stop_loss_percent=0.02),
    ExitOptimizerScenario("stop_loss_0.03%", stop_loss_percent=0.03),
    ExitOptimizerScenario("stop_loss_0.05%", stop_loss_percent=0.05),
    ExitOptimizerScenario(
        "max_holding_8h + stop_loss_0.03%",
        max_holding_seconds=8 * 60 * 60,
        stop_loss_percent=0.03,
    ),
    ExitOptimizerScenario(
        "max_holding_12h + stop_loss_0.03%",
        max_holding_seconds=12 * 60 * 60,
        stop_loss_percent=0.03,
    ),
)


@dataclass(frozen=True)
class ExitRuleOptimizerResult:
    scenario: str
    simulated_total_net: float
    automatic_target_closes: int
    forced_exits_count: int
    forced_exits_net: float
    manual_stale_cycles_avoided: int
    average_holding_time_seconds: float | None
    worst_loss: float | None
    recommendation_score: float


@dataclass(frozen=True)
class ExitRuleOptimizerReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    total_cycles: int
    scenarios: list[ExitRuleOptimizerResult]
    recommended_scenario: str | None


class ExitRuleOptimizerEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(
        self,
        *,
        profile: str,
        current_price: float,
        current_price_source: str = "UNKNOWN",
        current_price_timestamp: str = "UNKNOWN",
    ) -> ExitRuleOptimizerReport:
        cycles = self._load_profile_cycles(profile)
        snapshots = self._load_snapshots()
        current_timestamp = self._parse_current_timestamp(current_price_timestamp, cycles)
        results = [
            self._simulate_scenario(
                scenario=scenario,
                cycles=cycles,
                snapshots=snapshots,
                current_price=current_price,
                current_timestamp=current_timestamp,
            )
            for scenario in EXIT_OPTIMIZER_SCENARIOS
        ]
        recommended = max(results, key=lambda item: item.recommendation_score).scenario if results else None
        return ExitRuleOptimizerReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            total_cycles=len(cycles),
            scenarios=results,
            recommended_scenario=recommended,
        )

    def _simulate_scenario(
        self,
        *,
        scenario: ExitOptimizerScenario,
        cycles: list[dict],
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> ExitRuleOptimizerResult:
        pnls: list[float] = []
        holding_times: list[float] = []
        automatic_target_closes = 0
        forced_pnls: list[float] = []
        manual_stale_avoided = 0

        for cycle in cycles:
            result = self._simulate_cycle(
                scenario=scenario,
                cycle=cycle,
                snapshots=snapshots,
                current_price=current_price,
                current_timestamp=current_timestamp,
            )
            if result is None:
                continue
            event_type, pnl, exit_time = result
            pnls.append(pnl)
            holding_times.append(
                max(0.0, (exit_time - datetime.fromisoformat(cycle["opened_at"])).total_seconds())
            )
            if event_type == "TARGET":
                automatic_target_closes += 1
            elif event_type in {"STOP", "TIMEOUT"}:
                forced_pnls.append(pnl)
                if self._is_stale_manual(cycle):
                    manual_stale_avoided += 1

        simulated_total = sum(pnls)
        worst_loss = min(pnls) if pnls else None
        score = self._score(
            simulated_total_net=simulated_total,
            forced_exits_count=len(forced_pnls),
            manual_stale_cycles_avoided=manual_stale_avoided,
            worst_loss=worst_loss,
            average_holding_time_seconds=self._average(holding_times),
        )
        return ExitRuleOptimizerResult(
            scenario=scenario.name,
            simulated_total_net=simulated_total,
            automatic_target_closes=automatic_target_closes,
            forced_exits_count=len(forced_pnls),
            forced_exits_net=sum(forced_pnls),
            manual_stale_cycles_avoided=manual_stale_avoided,
            average_holding_time_seconds=self._average(holding_times),
            worst_loss=worst_loss,
            recommendation_score=score,
        )

    def _simulate_cycle(
        self,
        *,
        scenario: ExitOptimizerScenario,
        cycle: dict,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        actual_event = self._actual_event(cycle)
        forced_event = self._first_forced_event(
            scenario=scenario,
            cycle=cycle,
            snapshots=snapshots,
            current_price=current_price,
            current_timestamp=current_timestamp,
        )

        if forced_event is not None and (
            actual_event is None or forced_event[2] <= actual_event[2]
        ):
            event_type, exit_price, exit_time = forced_event
            return (event_type, self._pnl(cycle, exit_price), exit_time)

        if actual_event is not None:
            event_type, exit_price, exit_time = actual_event
            if event_type == "TARGET":
                return (event_type, cycle["net_profit"], exit_time)
            return (event_type, cycle["net_profit"], exit_time)
        return None

    def _actual_event(self, cycle: dict) -> tuple[str, float, datetime] | None:
        if not cycle.get("closed_at"):
            return None
        event_type = "TARGET" if cycle["status"] == "CLOSED" else "MANUAL"
        return (event_type, cycle["close_price"], datetime.fromisoformat(cycle["closed_at"]))

    def _first_forced_event(
        self,
        *,
        scenario: ExitOptimizerScenario,
        cycle: dict,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        events = [
            self._stop_event(
                scenario=scenario,
                cycle=cycle,
                snapshots=snapshots,
                current_price=current_price,
                current_timestamp=current_timestamp,
            ),
            self._timeout_event(
                scenario=scenario,
                cycle=cycle,
                snapshots=snapshots,
                current_price=current_price,
                current_timestamp=current_timestamp,
            ),
        ]
        candidates = [event for event in events if event is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[2], 0 if item[0] == "STOP" else 1))

    def _stop_event(
        self,
        *,
        scenario: ExitOptimizerScenario,
        cycle: dict,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        if scenario.stop_loss_percent is None:
            return None
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        closed_at = datetime.fromisoformat(cycle["closed_at"]) if cycle.get("closed_at") else None
        for snapshot in snapshots:
            if snapshot["timestamp"] < opened_at:
                continue
            if closed_at is not None and snapshot["timestamp"] > closed_at:
                break
            if (
                self._adverse_move_percent(
                    direction=cycle["direction"],
                    open_price=cycle["open_price"],
                    current_price=snapshot["price"],
                )
                >= scenario.stop_loss_percent
            ):
                return ("STOP", snapshot["price"], snapshot["timestamp"])

        if closed_at is None and (
            self._adverse_move_percent(
                direction=cycle["direction"],
                open_price=cycle["open_price"],
                current_price=current_price,
            )
            >= scenario.stop_loss_percent
        ):
            return ("STOP", current_price, current_timestamp)
        return None

    def _timeout_event(
        self,
        *,
        scenario: ExitOptimizerScenario,
        cycle: dict,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        if scenario.max_holding_seconds is None:
            return None
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        timeout_at = opened_at + timedelta(seconds=scenario.max_holding_seconds)
        closed_at = datetime.fromisoformat(cycle["closed_at"]) if cycle.get("closed_at") else None
        if closed_at is not None and closed_at <= timeout_at:
            return None
        if closed_at is None and current_timestamp < timeout_at:
            return None
        timeout_price = self._price_at_or_after(snapshots, timeout_at)
        if timeout_price is None:
            timeout_price = cycle["close_price"] if closed_at is not None else current_price
        return ("TIMEOUT", timeout_price, timeout_at)

    def _load_profile_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, net_profit,
                       opened_at, closed_at, close_reason
                FROM paper_cycles
                WHERE strategy_profile = ?
                ORDER BY opened_at ASC
                """,
                (profile,),
            ).fetchall()

        return [
            {
                "db_id": int(db_id),
                "cycle_id": int(cycle_id),
                "profile": clean_display_text(strategy_profile or "UNKNOWN"),
                "direction": clean_display_text(direction),
                "status": clean_display_text(status),
                "open_price": float(open_price),
                "close_price": float(close_price),
                "quantity": float(quantity),
                "net_profit": float(net_profit),
                "opened_at": clean_display_text(opened_at),
                "closed_at": clean_display_text(closed_at) if closed_at else None,
                "close_reason": clean_display_text(close_reason) if close_reason else None,
            }
            for (
                db_id,
                cycle_id,
                strategy_profile,
                direction,
                status,
                open_price,
                close_price,
                quantity,
                net_profit,
                opened_at,
                closed_at,
                close_reason,
            ) in rows
        ]

    def _load_snapshots(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()
        snapshots = []
        for timestamp, price in rows:
            try:
                parsed = datetime.fromisoformat(clean_display_text(timestamp))
            except ValueError:
                continue
            snapshots.append({"timestamp": parsed, "price": float(price)})
        return snapshots

    def _pnl(self, cycle: dict, exit_price: float) -> float:
        return self.fee_engine.calculate_profit(
            direction=cycle["direction"],
            open_price=cycle["open_price"],
            close_price=exit_price,
            quantity=cycle["quantity"],
            use_taker_fee=True,
        ).net_profit

    @staticmethod
    def _price_at_or_after(snapshots: list[dict], timestamp: datetime) -> float | None:
        for snapshot in snapshots:
            if snapshot["timestamp"] >= timestamp:
                return snapshot["price"]
        return None

    @staticmethod
    def _parse_current_timestamp(value: str, cycles: list[dict]) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = datetime.now()
        if cycles:
            latest_opened = max(datetime.fromisoformat(cycle["opened_at"]) for cycle in cycles)
            if parsed < latest_opened:
                return datetime.now()
        return parsed

    @staticmethod
    def _adverse_move_percent(direction: str, open_price: float, current_price: float) -> float:
        if open_price == 0.0:
            return 0.0
        if direction == "BUY_USDC":
            adverse = max(0.0, open_price - current_price)
        elif direction == "SELL_USDC":
            adverse = max(0.0, current_price - open_price)
        else:
            adverse = 0.0
        return adverse / open_price * 100.0

    @staticmethod
    def _is_stale_manual(cycle: dict) -> bool:
        return (
            cycle["status"] == "CLOSED_MANUAL"
            and clean_display_text(cycle.get("close_reason") or "").lower() == "stale"
        )

    @staticmethod
    def _score(
        *,
        simulated_total_net: float,
        forced_exits_count: int,
        manual_stale_cycles_avoided: int,
        worst_loss: float | None,
        average_holding_time_seconds: float | None,
    ) -> float:
        loss_penalty = abs(worst_loss) if worst_loss is not None and worst_loss < 0.0 else 0.0
        forced_penalty = forced_exits_count * 0.0001
        stale_bonus = manual_stale_cycles_avoided * 0.002
        holding_penalty = (average_holding_time_seconds or 0.0) / 86400.0 * 0.0001
        return simulated_total_net + stale_bonus - loss_penalty - forced_penalty - holding_penalty

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None
