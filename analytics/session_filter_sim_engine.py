from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


ALL_SESSIONS = {"ASIA", "LONDON", "NEW_YORK", "LONDON_NEW_YORK_OVERLAP"}


@dataclass(frozen=True)
class SessionFilterScenario:
    name: str
    allowed_sessions: set[str]


SESSION_FILTER_SCENARIOS = (
    SessionFilterScenario("all_sessions", set(ALL_SESSIONS)),
    SessionFilterScenario("new_york_only", {"NEW_YORK"}),
    SessionFilterScenario("london_only", {"LONDON"}),
    SessionFilterScenario("asia_only", {"ASIA"}),
    SessionFilterScenario("london_new_york_overlap_only", {"LONDON_NEW_YORK_OVERLAP"}),
    SessionFilterScenario("exclude_asia", ALL_SESSIONS - {"ASIA"}),
    SessionFilterScenario("exclude_london", ALL_SESSIONS - {"LONDON"}),
)


@dataclass(frozen=True)
class SessionFilterSimulationResult:
    scenario: str
    entries: int
    closed_cycles: int
    win_rate: float
    net_profit: float
    average_holding_time_seconds: float | None
    average_unrealized_pnl: float | None
    target_hit_rate: float
    current_open_cycle_blocked: bool
    historical_bad_cycles_blocked: bool
    recommendation_score: float


@dataclass(frozen=True)
class SessionFilterSimulationReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    total_cycles: int
    results: list[SessionFilterSimulationResult]
    recommended_scenario: str | None


class SessionFilterSimulationEngine:
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
    ) -> SessionFilterSimulationReport:
        cycles = self._load_profile_cycles(profile)
        results = [
            self._evaluate_scenario(
                scenario=scenario,
                cycles=cycles,
                current_price=current_price,
            )
            for scenario in SESSION_FILTER_SCENARIOS
        ]
        recommended = max(results, key=lambda item: item.recommendation_score).scenario if results else None
        return SessionFilterSimulationReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            total_cycles=len(cycles),
            results=results,
            recommended_scenario=recommended,
        )

    def _evaluate_scenario(
        self,
        *,
        scenario: SessionFilterScenario,
        cycles: list[dict],
        current_price: float,
    ) -> SessionFilterSimulationResult:
        kept = [
            cycle
            for cycle in cycles
            if cycle["session"] in scenario.allowed_sessions
        ]
        blocked = [
            cycle
            for cycle in cycles
            if cycle["session"] not in scenario.allowed_sessions
        ]
        closed = [cycle for cycle in kept if self._is_closed(cycle)]
        open_cycles = [cycle for cycle in kept if cycle["status"] == "OPEN"]
        wins = sum(1 for cycle in closed if cycle["net_profit"] > 0)
        target_hits = sum(1 for cycle in closed if cycle["status"] == "CLOSED")
        holding_times = [
            self._holding_time_seconds(cycle)
            for cycle in closed
            if self._holding_time_seconds(cycle) is not None
        ]
        unrealized = [
            self._unrealized_pnl(cycle, current_price)
            for cycle in open_cycles
        ]
        current_open_blocked = any(cycle["status"] == "OPEN" for cycle in blocked)
        bad_blocked = any(self._is_historical_bad_cycle(cycle) for cycle in blocked)
        win_rate = wins / len(closed) if closed else 0.0
        net_profit = sum(cycle["net_profit"] for cycle in closed)
        target_hit_rate = target_hits / len(kept) if kept else 0.0
        score = self._score(
            entries=len(kept),
            closed_cycles=len(closed),
            win_rate=win_rate,
            net_profit=net_profit,
            average_unrealized_pnl=self._average(unrealized),
            current_open_cycle_blocked=current_open_blocked,
            historical_bad_cycles_blocked=bad_blocked,
        )
        return SessionFilterSimulationResult(
            scenario=scenario.name,
            entries=len(kept),
            closed_cycles=len(closed),
            win_rate=win_rate,
            net_profit=net_profit,
            average_holding_time_seconds=self._average(holding_times),
            average_unrealized_pnl=self._average(unrealized),
            target_hit_rate=target_hit_rate,
            current_open_cycle_blocked=current_open_blocked,
            historical_bad_cycles_blocked=bad_blocked,
            recommendation_score=score,
        )

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

        cycles: list[dict] = []
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
        ) in rows:
            opened_at_text = clean_display_text(opened_at)
            if not self._can_parse_timestamp(opened_at_text):
                continue
            opened_hour = datetime.fromisoformat(opened_at_text).hour
            cycles.append(
                {
                    "db_id": int(db_id),
                    "cycle_id": int(cycle_id),
                    "profile": clean_display_text(strategy_profile or "UNKNOWN"),
                    "direction": clean_display_text(direction),
                    "status": clean_display_text(status),
                    "open_price": float(open_price),
                    "target_price": float(close_price),
                    "quantity": float(quantity),
                    "net_profit": float(net_profit),
                    "opened_at": opened_at_text,
                    "closed_at": clean_display_text(closed_at) if closed_at else None,
                    "session": self.classify_session(opened_hour),
                }
            )
        return cycles

    def _unrealized_pnl(self, cycle: dict, current_price: float) -> float:
        return self.fee_engine.calculate_profit(
            direction=cycle["direction"],
            open_price=cycle["open_price"],
            close_price=current_price,
            quantity=cycle["quantity"],
            use_taker_fee=True,
        ).net_profit

    @staticmethod
    def classify_session(hour: int) -> str:
        if 13 <= hour <= 16:
            return "LONDON_NEW_YORK_OVERLAP"
        if 8 <= hour <= 12:
            return "LONDON"
        if 17 <= hour <= 23:
            return "NEW_YORK"
        return "ASIA"

    @staticmethod
    def _is_closed(cycle: dict) -> bool:
        return cycle["status"] in {"CLOSED", "CLOSED_MANUAL"}

    @staticmethod
    def _is_historical_bad_cycle(cycle: dict) -> bool:
        if cycle["status"] not in {"CLOSED", "CLOSED_MANUAL"}:
            return False
        return cycle["status"] == "CLOSED_MANUAL" or cycle["net_profit"] <= 0

    @staticmethod
    def _holding_time_seconds(cycle: dict) -> float | None:
        if not cycle.get("closed_at"):
            return None
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        closed_at = datetime.fromisoformat(cycle["closed_at"])
        return max(0.0, (closed_at - opened_at).total_seconds())

    @staticmethod
    def _can_parse_timestamp(value: str) -> bool:
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return False
        return True

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _score(
        *,
        entries: int,
        closed_cycles: int,
        win_rate: float,
        net_profit: float,
        average_unrealized_pnl: float | None,
        current_open_cycle_blocked: bool,
        historical_bad_cycles_blocked: bool,
    ) -> float:
        sample_penalty = 0.002 if closed_cycles < 2 else 0.0
        open_bonus = 0.001 if current_open_cycle_blocked else 0.0
        bad_block_bonus = 0.001 if historical_bad_cycles_blocked else 0.0
        unrealized = average_unrealized_pnl or 0.0
        return (
            net_profit
            + win_rate * 0.01
            + unrealized
            + open_bonus
            + bad_block_bonus
            - sample_penalty
            + min(entries, 10) * 0.0001
        )
