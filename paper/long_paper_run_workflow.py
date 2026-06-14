from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from time import sleep

from analytics.validation_summary_engine import ValidationSummary
from analytics.validation_summary_engine import ValidationSummaryEngine
from app.bot_engine import BotEngine
from config.config_manager import BotConfig
from paper.paper_analytics_engine import PaperAnalytics
from paper.paper_analytics_engine import PaperAnalyticsEngine
from paper.paper_insights_engine import PaperInsights
from paper.paper_insights_engine import PaperInsightsEngine
from paper.paper_insights_exporter import PaperInsightsExporter
from paper.paper_report_exporter import PaperReportExporter
from paper.paper_trading_engine import PaperTradingEngine
from paper.paper_trading_engine import PaperTradingRunResult
from storage.database_manager import DatabaseManager
from strategy.profile_decision_engine import StrategyProfileDecisionEngine


@dataclass(frozen=True)
class LongPaperRunReportPaths:
    cycles_csv: Path
    safety_csv: Path
    summary_csv: Path
    insights_txt: Path


@dataclass(frozen=True)
class LongPaperRunResult:
    run_id: int
    long_run_id: int
    run_result: PaperTradingRunResult
    data_source: str
    stats: PaperAnalytics
    insights: PaperInsights
    validation_summary: ValidationSummary
    report_paths: LongPaperRunReportPaths
    strategy_profile: str = "strict_current"


class LongPaperRunWorkflow:
    def __init__(self, config: BotConfig, database: DatabaseManager) -> None:
        self.config = config
        self.database = database

    def run(
        self,
        iterations: int,
        interval_seconds: int = 0,
        strategy_profile: str = "strict_current",
        close_debug_callback: Callable[[dict], None] | None = None,
    ) -> LongPaperRunResult:
        if iterations <= 0:
            raise ValueError("iterations must be greater than 0.")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be 0 or greater.")

        bot = None
        if strategy_profile != "strict_current":
            bot = BotEngine()
            bot.decision_engine = StrategyProfileDecisionEngine(bot.config, strategy_profile)

        close_debug_kwargs = {}
        if close_debug_callback is not None:
            close_debug_kwargs["close_debug_callback"] = close_debug_callback

        if bot is None:
            engine = PaperTradingEngine(
                self.config,
                self.database,
                strategy_profile=strategy_profile,
                **close_debug_kwargs,
            )
        else:
            engine = PaperTradingEngine(
                self.config,
                self.database,
                bot=bot,
                strategy_profile=strategy_profile,
                **close_debug_kwargs,
            )
        if interval_seconds == 0:
            run_result = engine.run(iterations)
        else:
            run_result = self._run_with_interval(engine, iterations, interval_seconds)

        if strategy_profile == "strict_current":
            cycle_rows = self.database.load_recent_paper_cycles(limit=500)
        else:
            cycle_rows = self.database.load_recent_paper_cycles_by_profile(
                strategy_profile,
                limit=500,
            )
        safety_rows = self.database.load_recent_paper_safety_events(limit=500)
        stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)
        insights = PaperInsightsEngine().build(stats, safety_rows)
        run_id = self.database.save_paper_run(run_result, insights)
        insights_path = PaperInsightsExporter().export_txt(run_id, insights)

        exporter = PaperReportExporter()
        report_paths = LongPaperRunReportPaths(
            cycles_csv=exporter.export_cycles_csv(cycle_rows),
            safety_csv=exporter.export_safety_csv(safety_rows),
            summary_csv=exporter.export_summary_csv(stats, strategy_profile=strategy_profile),
            insights_txt=insights_path,
        )
        validation_summary = ValidationSummaryEngine(self.database, self.config).build_summary(
            profile=strategy_profile,
        )
        long_run_id = self.database.save_long_paper_run(
            iterations=iterations,
            interval_seconds=interval_seconds,
            final_value=run_result.final_portfolio.total_value,
            net_profit=stats.net_profit,
            win_rate=stats.win_rate,
            profit_factor=stats.profit_factor,
            validation_status=validation_summary.overall_status,
            insights_rating=insights.rating,
            summary_report_path=str(report_paths.summary_csv),
        )

        return LongPaperRunResult(
            run_id=run_id,
            long_run_id=long_run_id,
            run_result=run_result,
            data_source=run_result.data_source,
            stats=stats,
            insights=insights,
            validation_summary=validation_summary,
            report_paths=report_paths,
            strategy_profile=strategy_profile,
        )

    @staticmethod
    def _run_with_interval(
        engine: PaperTradingEngine,
        iterations: int,
        interval_seconds: int,
    ) -> PaperTradingRunResult:
        total_opened = 0
        total_closed = 0
        total_safety_stops = 0
        last_result = None
        data_sources: list[str] = []

        for index in range(iterations):
            last_result = engine.run(1)
            data_sources.append(last_result.data_source)
            total_opened += last_result.opened_cycles
            total_closed += last_result.closed_cycles
            total_safety_stops += last_result.safety_stops
            if last_result.safety_stops:
                break
            if index < iterations - 1:
                sleep(interval_seconds)

        if last_result is None:
            raise ValueError("No paper iterations were executed.")

        return PaperTradingRunResult(
            iterations=iterations,
            opened_cycles=total_opened,
            closed_cycles=total_closed,
            safety_stops=total_safety_stops,
            final_portfolio=last_result.final_portfolio,
            data_source=LongPaperRunWorkflow._combine_data_sources(data_sources),
        )

    @staticmethod
    def _combine_data_sources(data_sources: list[str]) -> str:
        if "FALLBACK" in data_sources:
            return "FALLBACK"
        if "BINANCE" in data_sources:
            return "BINANCE"
        if "MOCK" in data_sources:
            return "MOCK"
        return "UNKNOWN"
