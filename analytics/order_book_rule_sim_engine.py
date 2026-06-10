from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from analytics.filter_pass_diagnostics_engine import FilterPassDiagnosticsEngine
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


ORDER_BOOK_RULE_PROFILES = {
    "strict_current": {
        "BUY": {"BID_PRESSURE"},
        "SELL": {"ASK_PRESSURE"},
    },
    "allow_balanced": {
        "BUY": {"BID_PRESSURE", "BALANCED"},
        "SELL": {"ASK_PRESSURE", "BALANCED"},
    },
    "contrarian_pressure": {
        "BUY": {"ASK_PRESSURE", "BALANCED"},
        "SELL": {"BID_PRESSURE", "BALANCED"},
    },
    "ignore_order_book": {
        "BUY": {"BID_PRESSURE", "ASK_PRESSURE", "BALANCED", "UNKNOWN"},
        "SELL": {"BID_PRESSURE", "ASK_PRESSURE", "BALANCED", "UNKNOWN"},
    },
}


@dataclass(frozen=True)
class OrderBookRuleSimulationProfile:
    name: str
    total_entry_zone_samples: int
    buy_candidates: int
    sell_candidates: int
    pass_count: int
    pass_rate: float
    remaining_blocking_filters: list[tuple[str, int]]


@dataclass(frozen=True)
class OrderBookRuleSimulationReport:
    profiles: list[OrderBookRuleSimulationProfile]


class OrderBookRuleSimulationEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(self) -> OrderBookRuleSimulationReport:
        diagnostics = FilterPassDiagnosticsEngine(self.database, self.config)
        rows = diagnostics._load_entry_zone_rows()
        evaluated_rows = [diagnostics._evaluate_row(row) for row in rows]

        return OrderBookRuleSimulationReport(
            profiles=[
                self._build_profile(name, rules, evaluated_rows)
                for name, rules in ORDER_BOOK_RULE_PROFILES.items()
            ]
        )

    def _build_profile(
        self,
        name: str,
        rules: dict[str, set[str]],
        evaluated_rows: list[dict],
    ) -> OrderBookRuleSimulationProfile:
        blocking_filters: Counter[str] = Counter()
        pass_count = 0

        for row in evaluated_rows:
            filters = dict(row["filters"])
            filters["order_book_pressure"] = self._profile_order_book_pass(row, rules)
            failed_filters = [
                filter_name
                for filter_name, result in filters.items()
                if result is False
            ]
            if failed_filters:
                blocking_filters.update(failed_filters)
            else:
                pass_count += 1

        total = len(evaluated_rows)
        return OrderBookRuleSimulationProfile(
            name=name,
            total_entry_zone_samples=total,
            buy_candidates=sum(1 for row in evaluated_rows if row["zone"] == "BUY"),
            sell_candidates=sum(1 for row in evaluated_rows if row["zone"] == "SELL"),
            pass_count=pass_count,
            pass_rate=pass_count / total if total else 0.0,
            remaining_blocking_filters=sorted(
                blocking_filters.items(),
                key=lambda item: (-item[1], item[0]),
            ),
        )

    @staticmethod
    def _profile_order_book_pass(row: dict, rules: dict[str, set[str]]) -> bool | None:
        pressure = row["order_book_pressure"]
        if not pressure or pressure == "UNKNOWN":
            return True if "UNKNOWN" in rules[row["zone"]] else None
        return pressure in rules[row["zone"]]
