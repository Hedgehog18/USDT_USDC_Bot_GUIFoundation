from collections import Counter
from dataclasses import dataclass

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class BlockedDecision:
    timestamp: str
    decision: str
    reason: str
    risk_reason: str


@dataclass(frozen=True)
class RiskDiagnosticsSummary:
    total_audited_decisions: int
    allowed_count: int
    blocked_count: int
    blocked_rate: float
    top_risk_reasons: list[tuple[str, int]]
    blocked_action_distribution: dict[str, int]
    latest_blocked_decisions: list[BlockedDecision]


class RiskDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self, top: int = 5, latest: int = 5) -> RiskDiagnosticsSummary:
        rows = self._load_audit_rows()
        total = len(rows)
        allowed_count = sum(1 for row in rows if row["allowed"])
        blocked_rows = [row for row in rows if not row["allowed"]]
        blocked_count = len(blocked_rows)
        blocked_rate = blocked_count / total if total else 0.0

        return RiskDiagnosticsSummary(
            total_audited_decisions=total,
            allowed_count=allowed_count,
            blocked_count=blocked_count,
            blocked_rate=blocked_rate,
            top_risk_reasons=self._top_risk_reasons(blocked_rows, top),
            blocked_action_distribution=self._blocked_action_distribution(blocked_rows),
            latest_blocked_decisions=self._latest_blocked_decisions(blocked_rows, latest),
        )

    def _load_audit_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, decision, allowed, reason, risk_reason
                FROM decision_audit
                ORDER BY timestamp ASC
                """
            ).fetchall()
        return [
            {
                "timestamp": clean_display_text(timestamp),
                "decision": clean_display_text(decision),
                "allowed": bool(allowed),
                "reason": clean_display_text(reason),
                "risk_reason": clean_display_text(risk_reason),
            }
            for timestamp, decision, allowed, reason, risk_reason in rows
        ]

    @staticmethod
    def _top_risk_reasons(rows: list[dict], top: int) -> list[tuple[str, int]]:
        counter = Counter(row["risk_reason"] or "No risk reason" for row in rows)
        return counter.most_common(top)

    @staticmethod
    def _blocked_action_distribution(rows: list[dict]) -> dict[str, int]:
        counter = Counter((row["decision"] or "UNKNOWN").upper() for row in rows)
        return dict(sorted(counter.items()))

    @staticmethod
    def _latest_blocked_decisions(rows: list[dict], latest: int) -> list[BlockedDecision]:
        return [
            BlockedDecision(
                timestamp=row["timestamp"],
                decision=row["decision"],
                reason=row["reason"],
                risk_reason=row["risk_reason"],
            )
            for row in reversed(rows[-latest:])
        ]
