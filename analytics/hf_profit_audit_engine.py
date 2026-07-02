from __future__ import annotations

from dataclasses import dataclass

from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFProfitAuditCycle:
    db_id: int
    timestamp: str
    direction: str
    status: str
    open_price: float
    close_price: float
    quantity: float
    net_profit: float
    close_reason: str
    issue: str = ""


@dataclass(frozen=True)
class HFProfitAuditReport:
    profile: str
    since_id: int | None
    total_cycles: int
    closed_cycles: int
    total_net_profit: float
    latest_100_net_profit: float
    latest_250_net_profit: float
    latest_500_net_profit: float
    current_run_cycles: int
    current_run_net_profit: float
    extreme_close_cycles_count: int
    extreme_close_net_profit: float
    extreme_close_profit_share: float
    net_without_extreme_close_cycles: float
    best_cycle: HFProfitAuditCycle | None
    worst_cycle: HFProfitAuditCycle | None
    top_cycles: list[HFProfitAuditCycle]
    suspicious_cycles: list[HFProfitAuditCycle]
    abnormal_quantity_cycles: list[HFProfitAuditCycle]
    abnormal_distance_cycles: list[HFProfitAuditCycle]
    fallback_price_cycles: list[HFProfitAuditCycle]


class HFProfitAuditEngine:
    SUSPICIOUS_NET_THRESHOLD = 0.01
    ABNORMAL_QUANTITY_LIMIT = 20.0
    ABNORMAL_DISTANCE_LIMIT = 0.001
    FALLBACK_CLOSE_PRICES = {0.99992000}

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, profile: str, since_id: int | None = None) -> HFProfitAuditReport:
        rows = self._load_profile_cycles(profile)
        closed_rows = [row for row in rows if row["status"] in {"CLOSED", "CLOSED_MANUAL"}]
        current_rows = [
            row for row in closed_rows
            if since_id is not None and int(row["id"]) > since_id
        ]
        latest_100 = closed_rows[:100]
        latest_250 = closed_rows[:250]
        latest_500 = closed_rows[:500]
        top_rows = sorted(closed_rows, key=lambda row: float(row["net_profit"] or 0.0), reverse=True)[:10]
        total_net_profit = sum(float(row["net_profit"] or 0.0) for row in closed_rows)
        extreme_rows = [
            row for row in closed_rows
            if self._is_fallback_close_price(float(row["close_price"] or 0.0))
        ]
        extreme_net_profit = sum(float(row["net_profit"] or 0.0) for row in extreme_rows)

        return HFProfitAuditReport(
            profile=profile,
            since_id=since_id,
            total_cycles=len(rows),
            closed_cycles=len(closed_rows),
            total_net_profit=total_net_profit,
            latest_100_net_profit=sum(float(row["net_profit"] or 0.0) for row in latest_100),
            latest_250_net_profit=sum(float(row["net_profit"] or 0.0) for row in latest_250),
            latest_500_net_profit=sum(float(row["net_profit"] or 0.0) for row in latest_500),
            current_run_cycles=len(current_rows),
            current_run_net_profit=sum(float(row["net_profit"] or 0.0) for row in current_rows),
            extreme_close_cycles_count=len(extreme_rows),
            extreme_close_net_profit=extreme_net_profit,
            extreme_close_profit_share=self._profit_share(extreme_net_profit, total_net_profit),
            net_without_extreme_close_cycles=total_net_profit - extreme_net_profit,
            best_cycle=self._cycle(max(closed_rows, key=lambda row: float(row["net_profit"] or 0.0))) if closed_rows else None,
            worst_cycle=self._cycle(min(closed_rows, key=lambda row: float(row["net_profit"] or 0.0))) if closed_rows else None,
            top_cycles=[self._cycle(row) for row in top_rows],
            suspicious_cycles=[
                self._cycle(row, "unusually_high_net_profit")
                for row in closed_rows
                if float(row["net_profit"] or 0.0) >= self.SUSPICIOUS_NET_THRESHOLD
            ],
            abnormal_quantity_cycles=[
                self._cycle(row, "abnormal_quantity")
                for row in rows
                if float(row["quantity"] or 0.0) <= 0.0
                or float(row["quantity"] or 0.0) > self.ABNORMAL_QUANTITY_LIMIT
            ],
            abnormal_distance_cycles=[
                self._cycle(row, "abnormal_open_close_distance")
                for row in closed_rows
                if abs(float(row["close_price"] or 0.0) - float(row["open_price"] or 0.0)) > self.ABNORMAL_DISTANCE_LIMIT
            ],
            fallback_price_cycles=[
                self._cycle(row, "fallback_or_extreme_close_price")
                for row in closed_rows
                if self._is_fallback_close_price(float(row["close_price"] or 0.0))
            ],
        )

    def _load_profile_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, strategy_profile, direction, status,
                       open_price, close_price, quantity, net_profit, close_reason
                FROM paper_cycles
                WHERE strategy_profile = ?
                ORDER BY id DESC
                """,
                (profile,),
            ).fetchall()
        keys = (
            "id", "timestamp", "strategy_profile", "direction", "status",
            "open_price", "close_price", "quantity", "net_profit", "close_reason",
        )
        return [dict(zip(keys, row)) for row in rows]

    def _cycle(self, row: dict, issue: str = "") -> HFProfitAuditCycle:
        return HFProfitAuditCycle(
            db_id=int(row["id"]),
            timestamp=str(row["timestamp"]),
            direction=str(row["direction"]),
            status=str(row["status"]),
            open_price=float(row["open_price"] or 0.0),
            close_price=float(row["close_price"] or 0.0),
            quantity=float(row["quantity"] or 0.0),
            net_profit=float(row["net_profit"] or 0.0),
            close_reason=str(row["close_reason"] or ""),
            issue=issue,
        )

    def _is_fallback_close_price(self, close_price: float) -> bool:
        if close_price < 0.99 or close_price > 1.01:
            return True
        return any(abs(close_price - value) < 0.00000001 for value in self.FALLBACK_CLOSE_PRICES)

    def _profit_share(self, part: float, total: float) -> float:
        if total <= 0:
            return 0.0
        return part / total
