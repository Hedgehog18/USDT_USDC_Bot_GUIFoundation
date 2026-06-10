from dataclasses import dataclass

from analytics.decision_diagnostics_engine import DecisionDiagnosticsEngine
from analytics.risk_diagnostics_engine import RiskDiagnosticsEngine
from analytics.strategy_validation_engine import StrategyValidationEngine
from paper.paper_analytics_engine import PaperAnalyticsEngine
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class ValidationSummary:
    overall_status: str
    warnings: list[str]
    next_action: str
    strategy_signals: int
    latest_backtest_trades: int
    latest_backtest_net_profit: float
    paper_cycles: int
    paper_net_profit: float
    risk_blocked_rate: float


class ValidationSummaryEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self) -> ValidationSummary:
        strategy = StrategyValidationEngine(self.database).build_summary()
        decision = DecisionDiagnosticsEngine(self.database).build_summary()
        risk = RiskDiagnosticsEngine(self.database).build_summary()
        backtest = self._load_latest_backtest()
        paper = self._load_paper_stats()

        latest_backtest_trades = int(backtest[5]) if backtest else 0
        latest_backtest_net_profit = float(backtest[7]) if backtest else 0.0
        risk_blocked_rate = risk.blocked_rate

        warnings = self._build_warnings(
            strategy_signals=strategy.total_signals,
            decision_total=decision.total_decisions,
            latest_backtest_trades=latest_backtest_trades,
            latest_backtest_net_profit=latest_backtest_net_profit,
            paper_cycles=paper.total_cycles,
            paper_net_profit=paper.net_profit,
            risk_blocked_rate=risk_blocked_rate,
        )
        status = self._build_status(
            strategy_signals=strategy.total_signals,
            latest_backtest_trades=latest_backtest_trades,
            latest_backtest_net_profit=latest_backtest_net_profit,
            paper_cycles=paper.total_cycles,
            paper_net_profit=paper.net_profit,
            risk_blocked_rate=risk_blocked_rate,
        )

        return ValidationSummary(
            overall_status=status,
            warnings=warnings,
            next_action=self._next_action(status, warnings),
            strategy_signals=strategy.total_signals,
            latest_backtest_trades=latest_backtest_trades,
            latest_backtest_net_profit=latest_backtest_net_profit,
            paper_cycles=paper.total_cycles,
            paper_net_profit=paper.net_profit,
            risk_blocked_rate=risk_blocked_rate,
        )

    def _load_latest_backtest(self):
        try:
            return self.database.load_latest_backtest_run()
        except AttributeError:
            rows = self.database.load_recent_backtest_runs(limit=1)
            return rows[0] if rows else None
        except Exception:
            return None

    def _load_paper_stats(self):
        try:
            rows = self.database.load_recent_paper_cycles(limit=500)
        except Exception:
            rows = []
        return PaperAnalyticsEngine().build_from_rows(rows)

    @staticmethod
    def _build_warnings(
        strategy_signals: int,
        decision_total: int,
        latest_backtest_trades: int,
        latest_backtest_net_profit: float,
        paper_cycles: int,
        paper_net_profit: float,
        risk_blocked_rate: float,
    ) -> list[str]:
        warnings = []
        if strategy_signals == 0:
            warnings.append("No strategy signals")
        if decision_total == 0:
            warnings.append("No decision diagnostics data")
        if latest_backtest_trades == 0:
            warnings.append("No backtest trades")
        if latest_backtest_trades > 0 and latest_backtest_net_profit <= 0:
            warnings.append("Latest backtest net profit is not positive")
        if paper_cycles == 0:
            warnings.append("No paper cycles")
        elif paper_cycles < 20:
            warnings.append("Few paper cycles")
        if paper_cycles > 0 and paper_net_profit <= 0:
            warnings.append("Paper net profit is not positive")
        if risk_blocked_rate >= 0.9:
            warnings.append(f"Risk blocked rate is very high ({risk_blocked_rate * 100:.2f}%)")
        elif risk_blocked_rate >= 0.7:
            warnings.append(f"Risk blocked rate is elevated ({risk_blocked_rate * 100:.2f}%)")
        return warnings

    @staticmethod
    def _build_status(
        strategy_signals: int,
        latest_backtest_trades: int,
        latest_backtest_net_profit: float,
        paper_cycles: int,
        paper_net_profit: float,
        risk_blocked_rate: float,
    ) -> str:
        has_backtest = latest_backtest_trades > 0
        has_paper = paper_cycles > 0
        has_strategy = strategy_signals > 0

        if not has_backtest and not has_paper and not has_strategy:
            return "NO_DATA"

        if strategy_signals == 0 or latest_backtest_trades == 0 or risk_blocked_rate >= 0.9:
            return "WEAK"

        positive_backtest = latest_backtest_net_profit > 0
        positive_paper = has_paper and paper_net_profit > 0

        if positive_backtest and has_paper and risk_blocked_rate < 0.7:
            return "READY_FOR_LONG_PAPER"
        if (positive_backtest or positive_paper) and risk_blocked_rate < 0.8:
            return "PROMISING"
        return "MIXED"

    @staticmethod
    def _next_action(status: str, warnings: list[str]) -> str:
        if status == "NO_DATA":
            return "Run a backtest and paper-cycle-sim to collect validation data."
        if "No strategy signals" in warnings:
            return "Run Demo Runner or Paper Simulation to generate strategy signals."
        if "No backtest trades" in warnings:
            return "Run a backtest with enough candles before extending paper validation."
        if "No paper cycles" in warnings or "Few paper cycles" in warnings:
            return "Run paper-cycle-sim for 500+ iterations before real trading."
        if status == "WEAK":
            return "Review decision and risk diagnostics before more paper testing."
        if status == "MIXED":
            return "Run longer backtest and paper validation, then compare diagnostics."
        if status == "PROMISING":
            return "Run longer paper validation and monitor risk blocked rate."
        return "Continue long paper validation. Real trading remains disabled."
