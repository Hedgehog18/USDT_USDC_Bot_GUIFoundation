from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


SESSION_NAMES = ("ASIA", "LONDON", "NEW_YORK", "LONDON_NEW_YORK_OVERLAP")


@dataclass(frozen=True)
class MarketSessionStats:
    session: str
    total_entries: int
    closed_cycles: int
    open_cycles: int
    win_rate: float
    net_profit: float
    average_holding_time_seconds: float | None
    average_unrealized_pnl: float | None
    target_hit_rate: float


@dataclass(frozen=True)
class MarketSessionDiagnosticsReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    session_stats: list[MarketSessionStats]
    entry_hour_distribution: dict[int, int]
    close_hour_distribution: dict[int, int]


class MarketSessionDiagnosticsEngine:
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
    ) -> MarketSessionDiagnosticsReport:
        cycles = self._load_profile_cycles(profile)
        session_stats = [
            self._build_session_stats(session, cycles, current_price)
            for session in SESSION_NAMES
        ]
        return MarketSessionDiagnosticsReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            session_stats=session_stats,
            entry_hour_distribution=self._entry_hour_distribution(cycles),
            close_hour_distribution=self._close_hour_distribution(cycles),
        )

    def _build_session_stats(
        self,
        session: str,
        cycles: list[dict],
        current_price: float,
    ) -> MarketSessionStats:
        session_cycles = [
            cycle
            for cycle in cycles
            if self.classify_session(datetime.fromisoformat(cycle["opened_at"]).hour) == session
        ]
        closed = [cycle for cycle in session_cycles if self._is_closed(cycle)]
        open_cycles = [cycle for cycle in session_cycles if cycle["status"] == "OPEN"]
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
        return MarketSessionStats(
            session=session,
            total_entries=len(session_cycles),
            closed_cycles=len(closed),
            open_cycles=len(open_cycles),
            win_rate=wins / len(closed) if closed else 0.0,
            net_profit=sum(cycle["net_profit"] for cycle in closed),
            average_holding_time_seconds=self._average(holding_times),
            average_unrealized_pnl=self._average(unrealized),
            target_hit_rate=target_hits / len(session_cycles) if session_cycles else 0.0,
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
            closed_at_text = clean_display_text(closed_at) if closed_at else None
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
                    "closed_at": closed_at_text,
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
    def _holding_time_seconds(cycle: dict) -> float | None:
        if not cycle.get("closed_at"):
            return None
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        closed_at = datetime.fromisoformat(cycle["closed_at"])
        return max(0.0, (closed_at - opened_at).total_seconds())

    @staticmethod
    def _entry_hour_distribution(cycles: list[dict]) -> dict[int, int]:
        distribution = {hour: 0 for hour in range(24)}
        for cycle in cycles:
            distribution[datetime.fromisoformat(cycle["opened_at"]).hour] += 1
        return distribution

    @staticmethod
    def _close_hour_distribution(cycles: list[dict]) -> dict[int, int]:
        distribution = {hour: 0 for hour in range(24)}
        for cycle in cycles:
            if not cycle.get("closed_at"):
                continue
            distribution[datetime.fromisoformat(cycle["closed_at"]).hour] += 1
        return distribution

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
