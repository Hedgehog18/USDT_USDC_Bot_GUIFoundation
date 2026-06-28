from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class PaperOutlierValidationSummary:
    profile: str
    since_id: int
    total_cycles: int
    total_net: float
    best_cycle_net: float
    worst_cycle_net: float
    median_net: float
    trimmed_net_without_top_1: float
    trimmed_net_without_top_3: float
    trimmed_net_without_top_5: float
    winsorized_net_top_1_to_median: float
    winsorized_net_top_3_to_median: float
    positive_cycles_count: int
    negative_cycles_count: int
    breakeven_cycles_count: int
    target_closed_count: int
    timeout_closed_count: int
    target_net: float
    timeout_net: float
    net_without_outliers_positive_or_not: bool
    top1_profit_share: float
    top5_profit_share: float
    outlier_risk: str
    recommendation: str


class PaperOutlierValidationEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(
        self,
        *,
        profile: str,
        since_id: int = 0,
    ) -> PaperOutlierValidationSummary:
        cycles = self._load_realized_cycles(profile=profile, since_id=since_id)
        net_values = [cycle["net_profit"] for cycle in cycles]
        total_net = sum(net_values)
        median_net = median(net_values) if net_values else 0.0
        top_sorted = sorted(net_values, reverse=True)
        trimmed_top_1 = self._trimmed_net(total_net, top_sorted, 1)
        trimmed_top_3 = self._trimmed_net(total_net, top_sorted, 3)
        trimmed_top_5 = self._trimmed_net(total_net, top_sorted, 5)
        top1_share = self._profit_share(total_net, top_sorted, 1)
        top5_share = self._profit_share(total_net, top_sorted, 5)
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
        outlier_dependent = trimmed_top_1 <= 0.0 or top1_share > 0.50
        robust = trimmed_top_3 > 0.0 and top5_share < 0.50

        return PaperOutlierValidationSummary(
            profile=profile,
            since_id=since_id,
            total_cycles=len(cycles),
            total_net=total_net,
            best_cycle_net=max(net_values) if net_values else 0.0,
            worst_cycle_net=min(net_values) if net_values else 0.0,
            median_net=median_net,
            trimmed_net_without_top_1=trimmed_top_1,
            trimmed_net_without_top_3=trimmed_top_3,
            trimmed_net_without_top_5=trimmed_top_5,
            winsorized_net_top_1_to_median=self._winsorized_net(net_values, 1, median_net),
            winsorized_net_top_3_to_median=self._winsorized_net(net_values, 3, median_net),
            positive_cycles_count=sum(1 for value in net_values if value > 0.0),
            negative_cycles_count=sum(1 for value in net_values if value < 0.0),
            breakeven_cycles_count=sum(1 for value in net_values if value == 0.0),
            target_closed_count=len(target_cycles),
            timeout_closed_count=len(timeout_cycles),
            target_net=sum(cycle["net_profit"] for cycle in target_cycles),
            timeout_net=sum(cycle["net_profit"] for cycle in timeout_cycles),
            net_without_outliers_positive_or_not=trimmed_top_1 > 0.0,
            top1_profit_share=top1_share,
            top5_profit_share=top5_share,
            outlier_risk="OUTLIER_DEPENDENT" if outlier_dependent else "LOW",
            recommendation=self._recommendation(
                total_cycles=len(cycles),
                outlier_dependent=outlier_dependent,
                robust=robust,
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
    def _trimmed_net(total_net: float, top_sorted: list[float], count: int) -> float:
        return total_net - sum(top_sorted[:count])

    @staticmethod
    def _winsorized_net(values: list[float], top_count: int, replacement: float) -> float:
        if not values:
            return 0.0
        remaining_top = top_count
        total = 0.0
        top_values = sorted(values, reverse=True)[:top_count]
        top_value_counts = {value: top_values.count(value) for value in set(top_values)}
        for value in values:
            if value in top_value_counts and top_value_counts[value] > 0 and remaining_top > 0:
                total += replacement
                top_value_counts[value] -= 1
                remaining_top -= 1
            else:
                total += value
        return total

    @staticmethod
    def _profit_share(total_net: float, top_sorted: list[float], count: int) -> float:
        if total_net <= 0.0:
            return 0.0
        return sum(value for value in top_sorted[:count] if value > 0.0) / total_net

    @staticmethod
    def _recommendation(
        *,
        total_cycles: int,
        outlier_dependent: bool,
        robust: bool,
    ) -> str:
        if total_cycles == 0:
            return "NEEDS_MORE_DATA"
        if outlier_dependent:
            return "OUTLIER_DEPENDENT"
        if total_cycles < 100:
            return "NEEDS_MORE_DATA"
        if robust:
            return "ROBUST"
        return "NEEDS_MORE_DATA"
