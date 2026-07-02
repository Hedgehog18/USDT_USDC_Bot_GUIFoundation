from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from analytics.hf_extreme_price import KNOWN_HF_EXTREME_CLOSE_PRICES, is_extreme_close_price
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFExtremeMoveCycle:
    db_id: int
    timestamp: str
    direction: str
    open_price: float
    close_price: float
    net_profit: float
    close_reason: str
    holding_seconds: float | None
    is_extreme_close_price: bool


@dataclass(frozen=True)
class HFExtremeMoveWindow:
    label: str
    cycles_count: int
    net_profit: float
    extreme_cycles_count: int
    extreme_net_profit: float
    extreme_profit_share: float
    net_without_extreme_cycles: float


@dataclass(frozen=True)
class HFExtremeMoveDiagnosticsReport:
    profile: str
    total_cycles: int
    lifetime_net_profit: float
    extreme_cycles_count: int
    extreme_net_profit: float
    extreme_profit_share: float
    net_without_extreme_cycles: float
    known_extreme_close_prices: list[float]
    observed_min_close_price: float | None
    observed_max_close_price: float | None
    top_profit_cycles: list[HFExtremeMoveCycle]
    extreme_close_cycles: list[HFExtremeMoveCycle]
    best_extreme_cycle: HFExtremeMoveCycle | None
    worst_extreme_cycle: HFExtremeMoveCycle | None
    windows: list[HFExtremeMoveWindow]
    recommendation: str


class HFExtremeMoveDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, profile: str) -> HFExtremeMoveDiagnosticsReport:
        rows = self._load_closed_cycles(profile)
        close_prices = [float(row["close_price"] or 0.0) for row in rows]
        observed_min = min(close_prices) if close_prices else None
        observed_max = max(close_prices) if close_prices else None
        extreme_prices = self._extreme_prices(observed_min, observed_max)
        extreme_rows = [
            row for row in rows
            if self._is_extreme_close_price(float(row["close_price"] or 0.0), extreme_prices)
        ]
        top_rows = sorted(rows, key=lambda row: float(row["net_profit"] or 0.0), reverse=True)[:10]
        lifetime_net = self._sum_net(rows)
        extreme_net = self._sum_net(extreme_rows)
        extreme_cycles = [self._cycle(row, extreme_prices) for row in extreme_rows]

        return HFExtremeMoveDiagnosticsReport(
            profile=profile,
            total_cycles=len(rows),
            lifetime_net_profit=lifetime_net,
            extreme_cycles_count=len(extreme_rows),
            extreme_net_profit=extreme_net,
            extreme_profit_share=self._profit_share(extreme_net, lifetime_net),
            net_without_extreme_cycles=lifetime_net - extreme_net,
            known_extreme_close_prices=list(KNOWN_HF_EXTREME_CLOSE_PRICES),
            observed_min_close_price=observed_min,
            observed_max_close_price=observed_max,
            top_profit_cycles=[self._cycle(row, extreme_prices) for row in top_rows],
            extreme_close_cycles=extreme_cycles,
            best_extreme_cycle=max(extreme_cycles, key=lambda cycle: cycle.net_profit) if extreme_cycles else None,
            worst_extreme_cycle=min(extreme_cycles, key=lambda cycle: cycle.net_profit) if extreme_cycles else None,
            windows=[
                self._window("latest_100", rows[:100], extreme_prices),
                self._window("latest_250", rows[:250], extreme_prices),
                self._window("latest_500", rows[:500], extreme_prices),
                self._window("lifetime", rows, extreme_prices),
            ],
            recommendation=self._recommendation(self._profit_share(extreme_net, lifetime_net)),
        )

    def _load_closed_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, direction, status, open_price, close_price,
                       quantity, net_profit, opened_at, closed_at, close_reason
                FROM paper_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY id DESC
                """,
                (profile,),
            ).fetchall()
        keys = (
            "id", "timestamp", "direction", "status", "open_price", "close_price",
            "quantity", "net_profit", "opened_at", "closed_at", "close_reason",
        )
        return [dict(zip(keys, row)) for row in rows]

    def _cycle(self, row: dict, extreme_prices: set[float]) -> HFExtremeMoveCycle:
        close_price = float(row["close_price"] or 0.0)
        return HFExtremeMoveCycle(
            db_id=int(row["id"]),
            timestamp=str(row["timestamp"] or ""),
            direction=str(row["direction"] or ""),
            open_price=float(row["open_price"] or 0.0),
            close_price=close_price,
            net_profit=float(row["net_profit"] or 0.0),
            close_reason=str(row["close_reason"] or ""),
            holding_seconds=self._holding_seconds(row.get("opened_at"), row.get("closed_at")),
            is_extreme_close_price=self._is_extreme_close_price(close_price, extreme_prices),
        )

    def _window(
        self,
        label: str,
        rows: list[dict],
        extreme_prices: set[float],
    ) -> HFExtremeMoveWindow:
        extreme_rows = [
            row for row in rows
            if self._is_extreme_close_price(float(row["close_price"] or 0.0), extreme_prices)
        ]
        net = self._sum_net(rows)
        extreme_net = self._sum_net(extreme_rows)
        return HFExtremeMoveWindow(
            label=label,
            cycles_count=len(rows),
            net_profit=net,
            extreme_cycles_count=len(extreme_rows),
            extreme_net_profit=extreme_net,
            extreme_profit_share=self._profit_share(extreme_net, net),
            net_without_extreme_cycles=net - extreme_net,
        )

    def _extreme_prices(self, observed_min: float | None, observed_max: float | None) -> set[float]:
        prices = set(KNOWN_HF_EXTREME_CLOSE_PRICES)
        if observed_min is not None:
            prices.add(observed_min)
        if observed_max is not None:
            prices.add(observed_max)
        return prices

    def _is_extreme_close_price(self, close_price: float, extreme_prices: set[float]) -> bool:
        return is_extreme_close_price(close_price, extra_extreme_prices=extreme_prices)

    def _sum_net(self, rows: list[dict]) -> float:
        return sum(float(row["net_profit"] or 0.0) for row in rows)

    def _profit_share(self, part: float, total: float) -> float:
        if total <= 0:
            return 0.0
        return part / total

    def _recommendation(self, extreme_profit_share: float) -> str:
        if extreme_profit_share > 0.50:
            return "EXTREME_DEPENDENT"
        if extreme_profit_share >= 0.20:
            return "MODERATE_EXTREME_IMPACT"
        return "LOW_EXTREME_IMPACT"

    def _holding_seconds(self, opened_at: str | None, closed_at: str | None) -> float | None:
        if not opened_at or not closed_at:
            return None
        try:
            opened = datetime.fromisoformat(str(opened_at))
            closed = datetime.fromisoformat(str(closed_at))
        except ValueError:
            return None
        return max(0.0, (closed - opened).total_seconds())
