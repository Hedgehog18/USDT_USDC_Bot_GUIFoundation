from __future__ import annotations

from dataclasses import dataclass

from analytics.hf_extreme_price import is_extreme_close_price
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFCollectionExtremeMetrics:
    extreme_cycles: int
    non_extreme_cycles: int
    extreme_profit: float
    net_profit_without_extreme: float
    extreme_profit_share: float
    win_rate_without_extreme: float
    recommendation: str
    warning: str


class HFCollectionExtremeMetricsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_metrics(self, profile: str, baseline_max_id: int) -> HFCollectionExtremeMetrics:
        rows = self._load_closed_cycles(profile, baseline_max_id)
        extreme_rows = [
            row for row in rows
            if is_extreme_close_price(float(row["close_price"] or 0.0))
        ]
        non_extreme_rows = [
            row for row in rows
            if not is_extreme_close_price(float(row["close_price"] or 0.0))
        ]
        total_net = self._sum_net(rows)
        extreme_profit = self._sum_net(extreme_rows)
        no_extreme_profit = self._sum_net(non_extreme_rows)
        share = self._profit_share(extreme_profit, total_net)
        return HFCollectionExtremeMetrics(
            extreme_cycles=len(extreme_rows),
            non_extreme_cycles=len(non_extreme_rows),
            extreme_profit=extreme_profit,
            net_profit_without_extreme=no_extreme_profit,
            extreme_profit_share=share,
            win_rate_without_extreme=self._win_rate(non_extreme_rows),
            recommendation=self._recommendation(share),
            warning=self._warning(share),
        )

    def enrich_stats(
        self,
        stats: dict[str, float | int],
        profile: str,
        baseline_max_id: int,
    ) -> dict[str, float | int | str]:
        metrics = self.build_metrics(profile, baseline_max_id)
        enriched = dict(stats)
        enriched.update({
            "extreme_cycles": metrics.extreme_cycles,
            "non_extreme_cycles": metrics.non_extreme_cycles,
            "extreme_profit": metrics.extreme_profit,
            "net_profit_without_extreme": metrics.net_profit_without_extreme,
            "extreme_profit_share": metrics.extreme_profit_share,
            "win_rate_without_extreme": metrics.win_rate_without_extreme,
            "extreme_recommendation": metrics.recommendation,
            "extreme_warning": metrics.warning,
        })
        return enriched

    def _load_closed_cycles(self, profile: str, baseline_max_id: int) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, close_price, net_profit
                FROM paper_cycles
                WHERE strategy_profile = ?
                  AND id > ?
                  AND status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY id DESC
                """,
                (profile, baseline_max_id),
            ).fetchall()
        return [
            {"id": row[0], "close_price": row[1], "net_profit": row[2]}
            for row in rows
        ]

    def _sum_net(self, rows: list[dict]) -> float:
        return sum(float(row["net_profit"] or 0.0) for row in rows)

    def _win_rate(self, rows: list[dict]) -> float:
        if not rows:
            return 0.0
        wins = sum(1 for row in rows if float(row["net_profit"] or 0.0) > 0.0)
        return wins / len(rows)

    def _profit_share(self, part: float, total: float) -> float:
        if total <= 0:
            return 0.0
        return part / total

    def _recommendation(self, extreme_profit_share: float) -> str:
        if extreme_profit_share > 0.80:
            return "EXTREME_DEPENDENT_RUN"
        if extreme_profit_share < 0.20:
            return "NORMAL_HF_RUN"
        return "MODERATE_EXTREME_IMPACT_RUN"

    def _warning(self, extreme_profit_share: float) -> str:
        if extreme_profit_share > 0.50:
            return (
                "WARNING: New run is extreme-dependent. "
                "Do not evaluate ordinary HF performance using raw New Profit."
            )
        return ""
