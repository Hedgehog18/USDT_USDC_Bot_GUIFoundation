from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class PaperProfitConcentrationSummary:
    profile: str
    since_id: int
    realized_cycles_count: int
    total_net_profit: float
    best_cycle_net: float
    worst_cycle_net: float
    net_without_best_1: float
    net_without_best_3: float
    net_without_best_5: float
    top1_profit_share: float
    top3_profit_share: float
    top5_profit_share: float
    positive_cycles_count: int
    negative_cycles_count: int
    breakeven_cycles_count: int
    positive_net_total: float
    negative_net_total: float
    average_positive_cycle: float
    average_negative_cycle: float
    median_net: float
    target_closed_net: float
    timeout_closed_net: float
    target_closed_count: int
    timeout_closed_count: int
    timeout_loss_count: int
    timeout_avg_net: float
    recommendation: str


class PaperProfitConcentrationEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(
        self,
        *,
        profile: str,
        since_id: int = 0,
    ) -> PaperProfitConcentrationSummary:
        cycles = self._load_realized_cycles(profile=profile, since_id=since_id)
        net_values = [cycle["net_profit"] for cycle in cycles]
        positive_values = [value for value in net_values if value > 0.0]
        negative_values = [value for value in net_values if value < 0.0]
        target_cycles = [
            cycle
            for cycle in cycles
            if cycle["status"] == "CLOSED" and cycle["close_reason"] == "target"
        ]
        timeout_cycles = [
            cycle
            for cycle in cycles
            if cycle["status"] == "CLOSED" and cycle["close_reason"].startswith("max_holding_")
        ]

        total_net_profit = sum(net_values)
        top_sorted = sorted(net_values, reverse=True)
        net_without_best_1 = self._net_without_best(total_net_profit, top_sorted, 1)
        net_without_best_3 = self._net_without_best(total_net_profit, top_sorted, 3)
        net_without_best_5 = self._net_without_best(total_net_profit, top_sorted, 5)

        top1_share = self._profit_share(total_net_profit, top_sorted, 1)
        top3_share = self._profit_share(total_net_profit, top_sorted, 3)
        top5_share = self._profit_share(total_net_profit, top_sorted, 5)

        return PaperProfitConcentrationSummary(
            profile=profile,
            since_id=since_id,
            realized_cycles_count=len(cycles),
            total_net_profit=total_net_profit,
            best_cycle_net=max(net_values) if net_values else 0.0,
            worst_cycle_net=min(net_values) if net_values else 0.0,
            net_without_best_1=net_without_best_1,
            net_without_best_3=net_without_best_3,
            net_without_best_5=net_without_best_5,
            top1_profit_share=top1_share,
            top3_profit_share=top3_share,
            top5_profit_share=top5_share,
            positive_cycles_count=len(positive_values),
            negative_cycles_count=len(negative_values),
            breakeven_cycles_count=sum(1 for value in net_values if value == 0.0),
            positive_net_total=sum(positive_values),
            negative_net_total=sum(negative_values),
            average_positive_cycle=(
                sum(positive_values) / len(positive_values) if positive_values else 0.0
            ),
            average_negative_cycle=(
                sum(negative_values) / len(negative_values) if negative_values else 0.0
            ),
            median_net=median(net_values) if net_values else 0.0,
            target_closed_net=sum(cycle["net_profit"] for cycle in target_cycles),
            timeout_closed_net=sum(cycle["net_profit"] for cycle in timeout_cycles),
            target_closed_count=len(target_cycles),
            timeout_closed_count=len(timeout_cycles),
            timeout_loss_count=sum(1 for cycle in timeout_cycles if cycle["net_profit"] < 0.0),
            timeout_avg_net=(
                sum(cycle["net_profit"] for cycle in timeout_cycles) / len(timeout_cycles)
                if timeout_cycles
                else 0.0
            ),
            recommendation=self._recommendation(
                realized_count=len(cycles),
                net_without_best_1=net_without_best_1,
                top1_profit_share=top1_share,
                top5_profit_share=top5_share,
            ),
        )

    def _load_realized_cycles(self, *, profile: str, since_id: int) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, status, net_profit, close_reason
                FROM paper_cycles
                WHERE strategy_profile = ?
                  AND id > ?
                  AND status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY id ASC
                """,
                (profile, since_id),
            ).fetchall()

        cycles: list[dict] = []
        for db_id, status, net_profit, close_reason in rows:
            cycles.append(
                {
                    "db_id": int(db_id),
                    "status": clean_display_text(status),
                    "net_profit": float(net_profit),
                    "close_reason": clean_display_text(close_reason or ""),
                }
            )
        return cycles

    @staticmethod
    def _net_without_best(total_net_profit: float, top_sorted: list[float], count: int) -> float:
        return total_net_profit - sum(top_sorted[:count])

    @staticmethod
    def _profit_share(total_net_profit: float, top_sorted: list[float], count: int) -> float:
        if total_net_profit <= 0.0:
            return 0.0
        top_profit = sum(value for value in top_sorted[:count] if value > 0.0)
        return top_profit / total_net_profit

    @staticmethod
    def _recommendation(
        *,
        realized_count: int,
        net_without_best_1: float,
        top1_profit_share: float,
        top5_profit_share: float,
    ) -> str:
        if realized_count == 0:
            return "NO_DATA"
        if (
            top1_profit_share > 0.40
            or top5_profit_share > 0.70
            or net_without_best_1 <= 0.0
        ):
            return "HIGH_CONCENTRATION_RISK"
        if top1_profit_share > 0.25 or top5_profit_share > 0.50:
            return "MODERATE_CONCENTRATION"
        return "HEALTHY_DISTRIBUTION"
