from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


@dataclass(frozen=True)
class ExitRuleProfile:
    name: str
    stop_loss_percent: float | None = None
    max_holding_seconds: int | None = None


EXIT_RULE_PROFILES = (
    ExitRuleProfile("no_exit_rule"),
    ExitRuleProfile("stop_loss_0_02_percent", stop_loss_percent=0.02),
    ExitRuleProfile("stop_loss_0_03_percent", stop_loss_percent=0.03),
    ExitRuleProfile("stop_loss_0_05_percent", stop_loss_percent=0.05),
    ExitRuleProfile("max_holding_8h", max_holding_seconds=8 * 60 * 60),
    ExitRuleProfile("max_holding_24h", max_holding_seconds=24 * 60 * 60),
    ExitRuleProfile(
        "stop_loss_0_03_percent + max_holding_24h",
        stop_loss_percent=0.03,
        max_holding_seconds=24 * 60 * 60,
    ),
)


@dataclass(frozen=True)
class ExitRuleSimulationResult:
    rule_name: str
    closed_target_profit: float
    simulated_stop_timeout_losses: float
    combined_pnl: float
    win_rate: float
    max_loss: float | None
    avg_holding_time_seconds: float | None
    open_exposure_count: int
    open_exposure_notional: float
    recommendation_score: float


@dataclass(frozen=True)
class ExitRuleSimulationReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    total_cycles: int
    results: list[ExitRuleSimulationResult]
    recommended_rule: str | None


class ExitRuleSimulationEngine:
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
    ) -> ExitRuleSimulationReport:
        cycles = self._load_profile_cycles(profile)
        snapshots = self._load_snapshots()
        current_timestamp = self._parse_current_timestamp(current_price_timestamp)
        if cycles:
            latest_opened_at = max(datetime.fromisoformat(cycle["opened_at"]) for cycle in cycles)
            if current_timestamp < latest_opened_at:
                current_timestamp = datetime.now()
        results = [
            self._simulate_rule(
                rule=rule,
                cycles=cycles,
                snapshots=snapshots,
                current_price=current_price,
                current_timestamp=current_timestamp,
            )
            for rule in EXIT_RULE_PROFILES
        ]
        recommended = max(results, key=lambda item: item.recommendation_score).rule_name if results else None
        return ExitRuleSimulationReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            total_cycles=len(cycles),
            results=results,
            recommended_rule=recommended,
        )

    def _simulate_rule(
        self,
        *,
        rule: ExitRuleProfile,
        cycles: list[dict],
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> ExitRuleSimulationResult:
        target_pnls: list[float] = []
        simulated_pnls: list[float] = []
        closed_pnls: list[float] = []
        holding_times: list[float] = []
        open_exposure_count = 0
        open_exposure_notional = 0.0

        for cycle in cycles:
            event = self._first_exit_event(
                cycle=cycle,
                rule=rule,
                snapshots=snapshots,
                current_price=current_price,
                current_timestamp=current_timestamp,
            )
            if event is None:
                open_exposure_count += 1
                open_exposure_notional += cycle["quantity"] * current_price
                continue

            event_type, exit_price, exit_time = event
            pnl = self._pnl(cycle, exit_price)
            closed_pnls.append(pnl)
            holding_times.append(max(0.0, (exit_time - datetime.fromisoformat(cycle["opened_at"])).total_seconds()))
            if event_type == "TARGET":
                target_pnls.append(pnl)
            else:
                simulated_pnls.append(pnl)

        combined_pnl = sum(target_pnls) + sum(simulated_pnls)
        wins = sum(1 for pnl in closed_pnls if pnl > 0)
        win_rate = wins / len(closed_pnls) if closed_pnls else 0.0
        max_loss = min(closed_pnls) if closed_pnls else None
        score = self._score(
            combined_pnl=combined_pnl,
            win_rate=win_rate,
            max_loss=max_loss,
            open_exposure_count=open_exposure_count,
            simulated_exit_count=len(simulated_pnls),
            total_closed=len(closed_pnls),
        )
        return ExitRuleSimulationResult(
            rule_name=rule.name,
            closed_target_profit=sum(target_pnls),
            simulated_stop_timeout_losses=sum(simulated_pnls),
            combined_pnl=combined_pnl,
            win_rate=win_rate,
            max_loss=max_loss,
            avg_holding_time_seconds=self._average(holding_times),
            open_exposure_count=open_exposure_count,
            open_exposure_notional=open_exposure_notional,
            recommendation_score=score,
        )

    def _first_exit_event(
        self,
        *,
        cycle: dict,
        rule: ExitRuleProfile,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        closed_at = datetime.fromisoformat(cycle["closed_at"]) if cycle["closed_at"] else None
        target_event = ("TARGET", cycle["close_price"], closed_at) if closed_at else None
        stop_event = self._stop_event(cycle, rule, snapshots, current_price, current_timestamp)
        timeout_event = self._timeout_event(cycle, rule, snapshots, current_price, current_timestamp)

        candidates = [
            event
            for event in (stop_event, timeout_event, target_event)
            if event is not None and event[2] >= opened_at
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[2], 0 if item[0] == "STOP" else 1))

    def _stop_event(
        self,
        cycle: dict,
        rule: ExitRuleProfile,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        if rule.stop_loss_percent is None:
            return None
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        closed_at = datetime.fromisoformat(cycle["closed_at"]) if cycle["closed_at"] else None
        for snapshot in snapshots:
            if snapshot["timestamp"] < opened_at:
                continue
            if closed_at and snapshot["timestamp"] > closed_at:
                break
            if self._adverse_move_percent(cycle["direction"], cycle["open_price"], snapshot["price"]) >= rule.stop_loss_percent:
                return ("STOP", snapshot["price"], snapshot["timestamp"])

        if not closed_at and self._adverse_move_percent(cycle["direction"], cycle["open_price"], current_price) >= rule.stop_loss_percent:
            return ("STOP", current_price, current_timestamp)
        return None

    def _timeout_event(
        self,
        cycle: dict,
        rule: ExitRuleProfile,
        snapshots: list[dict],
        current_price: float,
        current_timestamp: datetime,
    ) -> tuple[str, float, datetime] | None:
        if rule.max_holding_seconds is None:
            return None
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        timeout_at = opened_at + timedelta(seconds=rule.max_holding_seconds)
        closed_at = datetime.fromisoformat(cycle["closed_at"]) if cycle["closed_at"] else None
        if closed_at and closed_at <= timeout_at:
            return None
        if not closed_at and current_timestamp < timeout_at:
            return None
        timeout_price = self._price_at_or_after(snapshots, timeout_at)
        if timeout_price is None:
            timeout_price = cycle["close_price"] if closed_at else current_price
        return ("TIMEOUT", timeout_price, timeout_at)

    def _load_profile_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, net_profit,
                       opened_at, closed_at
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
                parsed_timestamp = datetime.fromisoformat(clean_display_text(timestamp))
            except ValueError:
                continue
            snapshots.append({"timestamp": parsed_timestamp, "price": float(price)})
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
    def _parse_current_timestamp(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()

    @staticmethod
    def _adverse_move_percent(direction: str, open_price: float, current_price: float) -> float:
        if open_price == 0:
            return 0.0
        if direction == "BUY_USDC":
            adverse = max(0.0, open_price - current_price)
        elif direction == "SELL_USDC":
            adverse = max(0.0, current_price - open_price)
        else:
            adverse = 0.0
        return adverse / open_price * 100.0

    @staticmethod
    def _score(
        *,
        combined_pnl: float,
        win_rate: float,
        max_loss: float | None,
        open_exposure_count: int,
        simulated_exit_count: int,
        total_closed: int,
    ) -> float:
        loss_penalty = abs(max_loss) if max_loss is not None and max_loss < 0 else 0.0
        open_penalty = open_exposure_count * 0.001
        simulated_exit_penalty = (simulated_exit_count / total_closed) * 0.001 if total_closed else 0.0
        return combined_pnl + win_rate * 0.01 - loss_penalty - open_penalty - simulated_exit_penalty

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None
