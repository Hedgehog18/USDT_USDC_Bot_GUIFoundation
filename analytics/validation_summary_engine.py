from dataclasses import dataclass

from analytics.decision_diagnostics_engine import DecisionDiagnosticsEngine
from analytics.order_book_diagnostics_engine import OrderBookDiagnosticsEngine
from analytics.risk_diagnostics_engine import RiskDiagnosticsEngine
from analytics.strategy_validation_engine import StrategyValidationEngine
from config.config_manager import BotConfig, ConfigManager
from paper.paper_analytics_engine import PaperAnalyticsEngine
from paper.paper_insights_engine import PaperInsightsEngine
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class ValidationSummary:
    profile: str
    overall_status: str
    warnings: list[str]
    next_action: str
    strategy_signals: int
    latest_backtest_trades: int
    latest_backtest_net_profit: float
    paper_cycles: int
    paper_closed_cycles: int
    paper_net_profit: float
    paper_insights_rating: str
    risk_blocked_rate: float
    risk_blocked_rate_available: bool


class ValidationSummaryEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig | None = None) -> None:
        self.database = database
        self.config = config or ConfigManager().config

    def build_summary(self, profile: str = "strict_current") -> ValidationSummary:
        profile = profile or "strict_current"
        profile_aware = profile != "strict_current"
        strategy = StrategyValidationEngine(self.database).build_summary()
        decision = DecisionDiagnosticsEngine(self.database).build_summary()
        risk = RiskDiagnosticsEngine(self.database).build_summary() if not profile_aware else None
        order_book = OrderBookDiagnosticsEngine(self.database, self.config).build_summary()
        backtest = self._load_latest_backtest(profile=profile)
        paper = self._load_paper_stats(profile=profile)
        paper_insights = self._build_paper_insights(paper)

        latest_backtest_trades = int(backtest[5]) if backtest else 0
        latest_backtest_net_profit = float(backtest[7]) if backtest else 0.0
        risk_blocked_rate = risk.blocked_rate if risk else 0.0
        risk_blocked_rate_available = risk is not None

        warnings = self._build_warnings(
            profile=profile,
            strategy_signals=strategy.total_signals,
            decision_total=decision.total_decisions,
            latest_backtest_trades=latest_backtest_trades,
            latest_backtest_net_profit=latest_backtest_net_profit,
            paper_cycles=paper.total_cycles,
            paper_closed_cycles=paper.closed_cycles,
            paper_net_profit=paper.net_profit,
            paper_insights_rating=paper_insights.rating,
            risk_blocked_rate=risk_blocked_rate,
            risk_blocked_rate_available=risk_blocked_rate_available,
            entry_zone_snapshots=order_book.entry_zone_snapshots,
            matching_pressure_count=self._matching_pressure_count(order_book),
        )
        status = self._build_status(
            profile=profile,
            strategy_signals=strategy.total_signals,
            latest_backtest_trades=latest_backtest_trades,
            latest_backtest_net_profit=latest_backtest_net_profit,
            paper_cycles=paper.total_cycles,
            paper_closed_cycles=paper.closed_cycles,
            paper_net_profit=paper.net_profit,
            paper_insights_rating=paper_insights.rating,
            risk_blocked_rate=risk_blocked_rate,
            risk_blocked_rate_available=risk_blocked_rate_available,
        )

        return ValidationSummary(
            profile=profile,
            overall_status=status,
            warnings=warnings,
            next_action=self._next_action(status, warnings),
            strategy_signals=strategy.total_signals,
            latest_backtest_trades=latest_backtest_trades,
            latest_backtest_net_profit=latest_backtest_net_profit,
            paper_cycles=paper.total_cycles,
            paper_closed_cycles=paper.closed_cycles,
            paper_net_profit=paper.net_profit,
            paper_insights_rating=paper_insights.rating,
            risk_blocked_rate=risk_blocked_rate,
            risk_blocked_rate_available=risk_blocked_rate_available,
        )

    def _load_latest_backtest(self, profile: str = "strict_current"):
        if profile != "strict_current":
            return None
        try:
            return self.database.load_latest_backtest_run()
        except AttributeError:
            rows = self.database.load_recent_backtest_runs(limit=1)
            return rows[0] if rows else None
        except Exception:
            return None

    def _load_paper_stats(self, profile: str = "strict_current"):
        try:
            if profile == "strict_current":
                rows = self.database.load_recent_paper_cycles(limit=500)
            else:
                rows = self.database.load_recent_paper_cycles_by_profile(profile, limit=500)
        except Exception:
            rows = []
        return PaperAnalyticsEngine().build_from_rows(rows)

    def _build_paper_insights(self, paper):
        try:
            safety_rows = self.database.load_recent_paper_safety_events(limit=500)
        except Exception:
            safety_rows = []
        return PaperInsightsEngine().build(paper, safety_rows)

    @staticmethod
    def _build_warnings(
        profile: str,
        strategy_signals: int,
        decision_total: int,
        latest_backtest_trades: int,
        latest_backtest_net_profit: float,
        paper_cycles: int,
        paper_closed_cycles: int,
        paper_net_profit: float,
        paper_insights_rating: str,
        risk_blocked_rate: float,
        risk_blocked_rate_available: bool,
        entry_zone_snapshots: int,
        matching_pressure_count: int,
    ) -> list[str]:
        profile_aware = profile != "strict_current"
        warnings = []
        if strategy_signals == 0:
            warnings.append("No strategy signals")
        if decision_total == 0:
            warnings.append("No decision diagnostics data")
        if latest_backtest_trades == 0:
            if profile_aware:
                warnings.append("No profile-specific backtest trades")
            else:
                warnings.append("No backtest trades")
        if latest_backtest_trades > 0 and latest_backtest_net_profit <= 0:
            warnings.append("Latest backtest net profit is not positive")
        if paper_cycles == 0:
            warnings.append("No paper cycles")
        elif paper_closed_cycles < 20:
            warnings.append("Small sample size")
        if paper_closed_cycles > 0 and paper_net_profit <= 0:
            warnings.append("Paper net profit is not positive")
        if not risk_blocked_rate_available:
            warnings.append("Profile-specific risk blocked rate unavailable.")
        elif risk_blocked_rate >= 0.9:
            warnings.append(f"Risk blocked rate is very high ({risk_blocked_rate * 100:.2f}%)")
        elif risk_blocked_rate >= 0.7:
            warnings.append(f"Risk blocked rate is elevated ({risk_blocked_rate * 100:.2f}%)")
        if (
            not ValidationSummaryEngine._profile_ignores_order_book(profile)
            and entry_zone_snapshots > 0
            and matching_pressure_count == 0
        ):
            warnings.append("Entry zones detected, but order book never confirmed them.")
        return warnings

    @staticmethod
    def _matching_pressure_count(order_book_summary) -> int:
        return (
            order_book_summary.buy_zone_distribution.get("BID_PRESSURE", 0)
            + order_book_summary.sell_zone_distribution.get("ASK_PRESSURE", 0)
        )

    @staticmethod
    def _build_status(
        profile: str,
        strategy_signals: int,
        latest_backtest_trades: int,
        latest_backtest_net_profit: float,
        paper_cycles: int,
        paper_closed_cycles: int,
        paper_net_profit: float,
        paper_insights_rating: str,
        risk_blocked_rate: float,
        risk_blocked_rate_available: bool,
    ) -> str:
        profile_aware = profile != "strict_current"
        has_backtest = latest_backtest_trades > 0
        has_paper = paper_cycles > 0
        has_strategy = strategy_signals > 0

        if not has_backtest and not has_paper and not has_strategy:
            return "NO_DATA"

        if profile_aware:
            positive_paper = paper_closed_cycles > 0 and paper_net_profit > 0
            if positive_paper and paper_insights_rating in {"GOOD", "PROMISING"}:
                return "PROMISING" if paper_closed_cycles < 20 else "READY_FOR_LONG_PAPER"
            if positive_paper:
                return "MIXED"
            if paper_cycles > 0:
                return "MIXED"
            return "WEAK"

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
        if "No profile-specific backtest trades" in warnings and "Small sample size" not in warnings:
            return "Run profile-specific backtest/paper validation before comparing readiness."
        if "No paper cycles" in warnings or "Few paper cycles" in warnings or "Small sample size" in warnings:
            return "Run paper-cycle-sim for 500+ iterations before real trading."
        if status == "WEAK":
            return "Review decision and risk diagnostics before more paper testing."
        if status == "MIXED":
            return "Run longer backtest and paper validation, then compare diagnostics."
        if status == "PROMISING":
            return "Run longer paper validation and monitor risk blocked rate."
        return "Continue long paper validation. Real trading remains disabled."

    @staticmethod
    def _profile_ignores_order_book(profile: str) -> bool:
        return profile.startswith("mean_reversion_") or profile == "extreme_strategy_v1"

    @staticmethod
    def _profile_ignores_center_confidence(profile: str) -> bool:
        return profile.startswith("mean_reversion_") or profile == "extreme_strategy_v1"
