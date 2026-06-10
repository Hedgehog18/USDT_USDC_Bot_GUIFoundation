from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class DecisionDiagnosticsSummary:
    total_decisions: int
    buy_count: int
    sell_count: int
    wait_count: int
    top_wait_reasons: list[tuple[str, int]]
    top_buy_reasons: list[tuple[str, int]]
    top_sell_reasons: list[tuple[str, int]]
    confidence_distribution: dict[str, int]
    risk_blocked_count: int


class DecisionDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self, top: int = 5) -> DecisionDiagnosticsSummary:
        rows = self._load_trade_signal_rows()
        if not rows:
            rows = self._load_decision_audit_rows()

        total_decisions = len(rows)
        buy_count = sum(1 for row in rows if self._is_buy(row["decision"]))
        sell_count = sum(1 for row in rows if self._is_sell(row["decision"]))
        wait_count = sum(1 for row in rows if self._is_wait(row["decision"]))
        risk_blocked_count = sum(1 for row in rows if not row["allowed"])

        return DecisionDiagnosticsSummary(
            total_decisions=total_decisions,
            buy_count=buy_count,
            sell_count=sell_count,
            wait_count=wait_count,
            top_wait_reasons=self._top_reasons(rows, self._is_wait, top),
            top_buy_reasons=self._top_reasons(rows, self._is_buy, top),
            top_sell_reasons=self._top_reasons(rows, self._is_sell, top),
            confidence_distribution=self._confidence_distribution(rows),
            risk_blocked_count=risk_blocked_count,
        )

    def _load_trade_signal_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT action, reason, confidence, risk_allowed
                FROM trade_signals
                ORDER BY timestamp ASC
                """
            ).fetchall()
        return [
            {
                "decision": clean_display_text(action),
                "reason": clean_display_text(reason),
                "confidence": clean_display_text(confidence),
                "allowed": bool(risk_allowed),
            }
            for action, reason, confidence, risk_allowed in rows
        ]

    def _load_decision_audit_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT decision, reason, center_confidence, allowed
                FROM decision_audit
                ORDER BY timestamp ASC
                """
            ).fetchall()
        return [
            {
                "decision": clean_display_text(decision),
                "reason": clean_display_text(reason),
                "confidence": clean_display_text(confidence),
                "allowed": bool(allowed),
            }
            for decision, reason, confidence, allowed in rows
        ]

    @staticmethod
    def _is_buy(decision: str) -> bool:
        return str(decision).upper().startswith("BUY")

    @staticmethod
    def _is_sell(decision: str) -> bool:
        return str(decision).upper().startswith("SELL")

    @staticmethod
    def _is_wait(decision: str) -> bool:
        value = str(decision).upper()
        return value == "WAIT" or value == "SAFE_WAIT" or value.endswith("WAIT")

    def _top_reasons(self, rows: list[dict], predicate, top: int) -> list[tuple[str, int]]:
        counter = Counter(
            row["reason"] or "No reason"
            for row in rows
            if predicate(row["decision"])
        )
        return counter.most_common(top)

    @staticmethod
    def _confidence_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter((row["confidence"] or "UNKNOWN").upper() for row in rows)
        return dict(sorted(counter.items()))
