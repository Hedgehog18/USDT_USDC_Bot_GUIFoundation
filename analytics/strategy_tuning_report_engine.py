from collections import Counter
from dataclasses import dataclass

from analytics.confidence_diagnostics_engine import ConfidenceDiagnosticsEngine
from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


DEFAULT_THRESHOLDS = (0.2, 0.3, 0.4, 0.5, 0.6)


@dataclass(frozen=True)
class StrategyTuningThresholdResult:
    threshold: float
    total_passed: int
    pass_rate: float
    buy_candidates: int
    sell_candidates: int
    wait_still_blocked: int
    top_remaining_reasons: list[tuple[str, int]]


@dataclass(frozen=True)
class StrategyTuningReport:
    total_signals: int
    thresholds: list[StrategyTuningThresholdResult]


class StrategyTuningReportEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(
        self,
        thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
        top: int = 5,
    ) -> StrategyTuningReport:
        rows = self._load_signal_rows()
        total = len(rows)

        results = [
            self._build_threshold_result(rows, threshold, total, top)
            for threshold in thresholds
        ]
        return StrategyTuningReport(total_signals=total, thresholds=results)

    def _load_signal_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT action, reason, confidence
                FROM trade_signals
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            {
                "action": clean_display_text(action),
                "reason": clean_display_text(reason),
                "confidence_score": ConfidenceDiagnosticsEngine._confidence_to_score(
                    clean_display_text(confidence)
                ),
            }
            for action, reason, confidence in rows
        ]

    def _build_threshold_result(
        self,
        rows: list[dict],
        threshold: float,
        total: int,
        top: int,
    ) -> StrategyTuningThresholdResult:
        passed_rows = [row for row in rows if row["confidence_score"] >= threshold]
        remaining_rows = [row for row in rows if row["confidence_score"] < threshold]

        return StrategyTuningThresholdResult(
            threshold=threshold,
            total_passed=len(passed_rows),
            pass_rate=(len(passed_rows) / total) if total else 0.0,
            buy_candidates=sum(1 for row in passed_rows if self._is_buy(row["action"])),
            sell_candidates=sum(1 for row in passed_rows if self._is_sell(row["action"])),
            wait_still_blocked=sum(1 for row in remaining_rows if self._is_wait(row["action"])),
            top_remaining_reasons=self._top_reasons(remaining_rows, top),
        )

    @staticmethod
    def _top_reasons(rows: list[dict], top: int) -> list[tuple[str, int]]:
        counter = Counter(row["reason"] or "No reason" for row in rows)
        return counter.most_common(top)

    @staticmethod
    def _is_buy(action: str) -> bool:
        return str(action).upper().startswith("BUY")

    @staticmethod
    def _is_sell(action: str) -> bool:
        return str(action).upper().startswith("SELL")

    @staticmethod
    def _is_wait(action: str) -> bool:
        value = str(action).upper()
        return value == "WAIT" or value == "SAFE_WAIT" or value.endswith("WAIT")
