from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from analytics.market_session_diagnostics_engine import (
    SESSION_NAMES,
    MarketSessionDiagnosticsEngine,
)
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class ProfileCycleSummary:
    db_id: int
    direction: str
    status: str
    net_profit: float
    opened_at: str
    closed_at: str | None
    close_reason: str | None


@dataclass(frozen=True)
class ProfileBreakdown:
    name: str
    total_cycles: int
    automatic_closed_count: int
    manual_closed_count: int
    open_count: int
    net_profit: float
    win_rate: float


@dataclass(frozen=True)
class ProfilePerformanceSummary:
    profile: str
    total_profile_cycles: int
    automatic_closed_count: int
    manual_closed_count: int
    open_count: int
    total_realized_net_profit: float
    automatic_closed_net_profit: float
    manual_closed_net_profit: float
    target_hit_win_rate: float
    real_outcome_win_rate: float
    profitable_cycles_count: int
    breakeven_cycles_count: int
    losing_cycles_count: int
    average_profit: float
    average_loss: float
    average_cycle_pnl: float
    expectancy: float
    profit_factor: float
    timeout_closed_count: int
    timeout_profit_count: int
    timeout_breakeven_count: int
    timeout_loss_count: int
    timeout_average_pnl: float
    timeout_max_profit: float
    timeout_max_loss: float
    target_closed_count: int
    target_total_profit: float
    target_average_profit: float
    average_net_per_cycle: float
    best_cycle: ProfileCycleSummary | None
    worst_cycle: ProfileCycleSummary | None
    average_holding_time_seconds: float | None
    average_holding_time_automatic_seconds: float | None
    average_holding_time_manual_seconds: float | None
    manual_close_rate: float
    stale_close_count: int
    buy_breakdown: ProfileBreakdown
    sell_breakdown: ProfileBreakdown
    session_breakdown: list[ProfileBreakdown]
    recommendation: str


class ProfilePerformanceSummaryEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self, profile: str) -> ProfilePerformanceSummary:
        cycles = self._load_profile_cycles(profile)
        automatic = [cycle for cycle in cycles if cycle["status"] == "CLOSED"]
        manual = [cycle for cycle in cycles if cycle["status"] == "CLOSED_MANUAL"]
        open_cycles = [cycle for cycle in cycles if cycle["status"] == "OPEN"]
        realized = automatic + manual

        total_realized_net_profit = self._sum_net(realized)
        automatic_net_profit = self._sum_net(automatic)
        manual_net_profit = self._sum_net(manual)
        positive_values = [float(cycle["net_profit"]) for cycle in realized if cycle["net_profit"] > 0.0]
        breakeven_count = sum(1 for cycle in realized if cycle["net_profit"] == 0.0)
        negative_values = [float(cycle["net_profit"]) for cycle in realized if cycle["net_profit"] < 0.0]
        timeout_cycles = [cycle for cycle in realized if self._is_timeout_reason(cycle.get("close_reason"))]
        timeout_values = [float(cycle["net_profit"]) for cycle in timeout_cycles]
        timeout_positive = [value for value in timeout_values if value > 0.0]
        timeout_negative = [value for value in timeout_values if value < 0.0]
        target_cycles = [cycle for cycle in realized if cycle.get("close_reason") == "target"]
        target_total_profit = self._sum_net(target_cycles)
        best_cycle = self._cycle_summary(max(realized, key=lambda item: item["net_profit"])) if realized else None
        worst_cycle = self._cycle_summary(min(realized, key=lambda item: item["net_profit"])) if realized else None
        stale_close_count = sum(
            1
            for cycle in manual
            if clean_display_text(cycle.get("close_reason") or "").lower() == "stale"
        )

        return ProfilePerformanceSummary(
            profile=profile,
            total_profile_cycles=len(cycles),
            automatic_closed_count=len(automatic),
            manual_closed_count=len(manual),
            open_count=len(open_cycles),
            total_realized_net_profit=total_realized_net_profit,
            automatic_closed_net_profit=automatic_net_profit,
            manual_closed_net_profit=manual_net_profit,
            target_hit_win_rate=self._win_rate(automatic),
            real_outcome_win_rate=self._win_rate(realized),
            profitable_cycles_count=len(positive_values),
            breakeven_cycles_count=breakeven_count,
            losing_cycles_count=len(negative_values),
            average_profit=(sum(positive_values) / len(positive_values)) if positive_values else 0.0,
            average_loss=(sum(negative_values) / len(negative_values)) if negative_values else 0.0,
            average_cycle_pnl=(total_realized_net_profit / len(realized)) if realized else 0.0,
            expectancy=self._expectancy(realized),
            profit_factor=self._profit_factor(realized),
            timeout_closed_count=len(timeout_cycles),
            timeout_profit_count=len(timeout_positive),
            timeout_breakeven_count=sum(1 for value in timeout_values if value == 0.0),
            timeout_loss_count=len(timeout_negative),
            timeout_average_pnl=(sum(timeout_values) / len(timeout_values)) if timeout_values else 0.0,
            timeout_max_profit=max(timeout_positive) if timeout_positive else 0.0,
            timeout_max_loss=min(timeout_negative) if timeout_negative else 0.0,
            target_closed_count=len(target_cycles),
            target_total_profit=target_total_profit,
            target_average_profit=(target_total_profit / len(target_cycles)) if target_cycles else 0.0,
            average_net_per_cycle=(
                total_realized_net_profit / len(cycles)
                if cycles
                else 0.0
            ),
            best_cycle=best_cycle,
            worst_cycle=worst_cycle,
            average_holding_time_seconds=self._average_holding_time(realized),
            average_holding_time_automatic_seconds=self._average_holding_time(automatic),
            average_holding_time_manual_seconds=self._average_holding_time(manual),
            manual_close_rate=len(manual) / len(realized) if realized else 0.0,
            stale_close_count=stale_close_count,
            buy_breakdown=self._build_breakdown("BUY_USDC", cycles),
            sell_breakdown=self._build_breakdown("SELL_USDC", cycles),
            session_breakdown=self._build_session_breakdown(cycles),
            recommendation=self._recommendation(
                realized_count=len(realized),
                total_realized_net_profit=total_realized_net_profit,
                manual_close_rate=len(manual) / len(realized) if realized else 0.0,
                manual_net_profit=manual_net_profit,
                stale_close_count=stale_close_count,
                open_count=len(open_cycles),
            ),
        )

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
            close_reason,
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
                    "close_price": float(close_price),
                    "quantity": float(quantity),
                    "net_profit": float(net_profit),
                    "opened_at": opened_at_text,
                    "closed_at": closed_at_text,
                    "close_reason": clean_display_text(close_reason) if close_reason else None,
                }
            )
        return cycles

    def _build_breakdown(self, name: str, cycles: list[dict]) -> ProfileBreakdown:
        matching = [cycle for cycle in cycles if cycle["direction"] == name]
        return self._breakdown(name, matching)

    def _build_session_breakdown(self, cycles: list[dict]) -> list[ProfileBreakdown]:
        rows: list[ProfileBreakdown] = []
        for session in SESSION_NAMES:
            matching = [
                cycle
                for cycle in cycles
                if MarketSessionDiagnosticsEngine.classify_session(
                    datetime.fromisoformat(cycle["opened_at"]).hour
                ) == session
            ]
            rows.append(self._breakdown(session, matching))
        return rows

    def _breakdown(self, name: str, cycles: list[dict]) -> ProfileBreakdown:
        closed = [cycle for cycle in cycles if cycle["status"] in {"CLOSED", "CLOSED_MANUAL"}]
        return ProfileBreakdown(
            name=name,
            total_cycles=len(cycles),
            automatic_closed_count=sum(1 for cycle in cycles if cycle["status"] == "CLOSED"),
            manual_closed_count=sum(1 for cycle in cycles if cycle["status"] == "CLOSED_MANUAL"),
            open_count=sum(1 for cycle in cycles if cycle["status"] == "OPEN"),
            net_profit=self._sum_net(closed),
            win_rate=self._win_rate(closed),
        )

    @staticmethod
    def _cycle_summary(cycle: dict) -> ProfileCycleSummary:
        return ProfileCycleSummary(
            db_id=int(cycle["db_id"]),
            direction=cycle["direction"],
            status=cycle["status"],
            net_profit=float(cycle["net_profit"]),
            opened_at=cycle["opened_at"],
            closed_at=cycle.get("closed_at"),
            close_reason=cycle.get("close_reason"),
        )

    @staticmethod
    def _sum_net(cycles: list[dict]) -> float:
        return sum(float(cycle["net_profit"]) for cycle in cycles)

    @staticmethod
    def _win_rate(cycles: list[dict]) -> float:
        if not cycles:
            return 0.0
        return sum(1 for cycle in cycles if cycle["net_profit"] > 0.0) / len(cycles)

    @staticmethod
    def _profit_factor(cycles: list[dict]) -> float:
        positive = sum(float(cycle["net_profit"]) for cycle in cycles if cycle["net_profit"] > 0.0)
        negative = abs(sum(float(cycle["net_profit"]) for cycle in cycles if cycle["net_profit"] < 0.0))
        return (positive / negative) if negative > 0.0 else (positive if positive > 0.0 else 0.0)

    @classmethod
    def _expectancy(cls, cycles: list[dict]) -> float:
        if not cycles:
            return 0.0
        positive_values = [float(cycle["net_profit"]) for cycle in cycles if cycle["net_profit"] > 0.0]
        negative_values = [float(cycle["net_profit"]) for cycle in cycles if cycle["net_profit"] < 0.0]
        average_profit = (sum(positive_values) / len(positive_values)) if positive_values else 0.0
        average_loss = (sum(negative_values) / len(negative_values)) if negative_values else 0.0
        win_rate = len(positive_values) / len(cycles)
        loss_rate = len(negative_values) / len(cycles)
        return (win_rate * average_profit) + (loss_rate * average_loss)

    @staticmethod
    def _is_timeout_reason(reason: str | None) -> bool:
        if not reason:
            return False
        clean_reason = clean_display_text(reason).lower()
        return clean_reason.startswith("max_holding_") or "timeout" in clean_reason

    @classmethod
    def _average_holding_time(cls, cycles: list[dict]) -> float | None:
        values = [
            cls._holding_time_seconds(cycle)
            for cycle in cycles
            if cls._holding_time_seconds(cycle) is not None
        ]
        return sum(values) / len(values) if values else None

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
    def _recommendation(
        *,
        realized_count: int,
        total_realized_net_profit: float,
        manual_close_rate: float,
        manual_net_profit: float,
        stale_close_count: int,
        open_count: int,
    ) -> str:
        if realized_count < 50:
            return "NEEDS_MORE_DATA"
        if (
            stale_close_count > 0
            or manual_net_profit < 0.0
            or manual_close_rate >= 0.10
            or open_count > 0
        ):
            return "NEEDS_EXIT_RULE"
        if total_realized_net_profit > 0.0:
            return "READY_FOR_LONG_PAPER"
        return "NEEDS_MORE_DATA"
