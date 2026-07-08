from __future__ import annotations

from dataclasses import dataclass

from analytics.hf_extreme_price import is_extreme_close_price
from storage.database_manager import DatabaseManager


EXTREME_PROFILE = "extreme_strategy_v1"


@dataclass(frozen=True)
class ExtremeLateEntryCycle:
    db_id: int
    direction: str
    open_price: float
    close_price: float
    net_profit: float
    close_reason: str
    opened_at: str
    closed_at: str | None
    lead_warning: str
    velocity_value: float | None
    velocity_threshold: float | None
    compression_score: float | None
    opened_on_extreme_price: bool
    late_entry: bool


@dataclass(frozen=True)
class ExtremeLateEntryDiagnosticsReport:
    profile: str
    total_cycles: int
    late_entry_cycles: list[ExtremeLateEntryCycle]
    extreme_price_entry_cycles: list[ExtremeLateEntryCycle]
    late_entry_loss_contribution: float
    extreme_price_entry_loss_contribution: float
    total_net: float
    net_without_late_entry_cycles: float
    net_without_extreme_price_entries: float
    worst_cycle: ExtremeLateEntryCycle | None
    recommendation: str


class ExtremeLateEntryDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, profile: str = EXTREME_PROFILE) -> ExtremeLateEntryDiagnosticsReport:
        cycles = self._load_cycles(profile)
        late_cycles = [cycle for cycle in cycles if cycle.late_entry]
        extreme_price_cycles = [cycle for cycle in cycles if cycle.opened_on_extreme_price]
        total_net = self._sum_net(cycles)
        return ExtremeLateEntryDiagnosticsReport(
            profile=profile,
            total_cycles=len(cycles),
            late_entry_cycles=late_cycles,
            extreme_price_entry_cycles=extreme_price_cycles,
            late_entry_loss_contribution=self._sum_losses(late_cycles),
            extreme_price_entry_loss_contribution=self._sum_losses(extreme_price_cycles),
            total_net=total_net,
            net_without_late_entry_cycles=total_net - self._sum_net(late_cycles),
            net_without_extreme_price_entries=total_net - self._sum_net(extreme_price_cycles),
            worst_cycle=min(cycles, key=lambda cycle: cycle.net_profit, default=None),
            recommendation=self._recommendation(cycles, late_cycles, extreme_price_cycles),
        )

    def _load_cycles(self, profile: str) -> list[ExtremeLateEntryCycle]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id, c.direction, c.open_price, c.close_price, c.net_profit,
                    c.close_reason, c.opened_at, c.closed_at,
                    d.lead_warning, d.velocity_value, d.velocity_threshold,
                    d.compression_score
                FROM paper_cycles c
                LEFT JOIN hf_paper_cycle_entry_diagnostics d ON d.paper_cycle_id = c.id
                WHERE c.strategy_profile = ?
                  AND c.status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY c.id ASC
                """,
                (profile,),
            ).fetchall()
        cycles: list[ExtremeLateEntryCycle] = []
        for row in rows:
            open_price = float(row[2] or 0.0)
            lead_warning = str(row[8] or "N/A")
            opened_on_extreme_price = is_extreme_close_price(open_price)
            cycles.append(ExtremeLateEntryCycle(
                db_id=int(row[0]),
                direction=str(row[1] or "N/A"),
                open_price=open_price,
                close_price=float(row[3] or 0.0),
                net_profit=float(row[4] or 0.0),
                close_reason=str(row[5] or "N/A"),
                opened_at=str(row[6] or "N/A"),
                closed_at=str(row[7]) if row[7] is not None else None,
                lead_warning=lead_warning,
                velocity_value=self._optional_float(row[9]),
                velocity_threshold=self._optional_float(row[10]),
                compression_score=self._optional_float(row[11]),
                opened_on_extreme_price=opened_on_extreme_price,
                late_entry=lead_warning.lower() == "yes" or opened_on_extreme_price,
            ))
        return cycles

    @staticmethod
    def _sum_net(cycles: list[ExtremeLateEntryCycle]) -> float:
        return sum(cycle.net_profit for cycle in cycles)

    @staticmethod
    def _sum_losses(cycles: list[ExtremeLateEntryCycle]) -> float:
        return sum(cycle.net_profit for cycle in cycles if cycle.net_profit < 0.0)

    @staticmethod
    def _optional_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _recommendation(
        self,
        cycles: list[ExtremeLateEntryCycle],
        late_cycles: list[ExtremeLateEntryCycle],
        extreme_price_cycles: list[ExtremeLateEntryCycle],
    ) -> str:
        if len(cycles) < 20:
            return "NEED_MORE_DATA"
        if self._sum_losses(extreme_price_cycles) < 0.0:
            return "BLOCK_EXTREME_PRICE_ENTRIES"
        if self._sum_losses(late_cycles) < 0.0:
            return "TUNE_LATE_ENTRY_GUARD"
        return "KEEP_COLLECTING"
