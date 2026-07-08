import argparse

import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from backtest.backtest_comparison_engine import BacktestComparisonEngine
from backtest.backtest_comparison_exporter import BacktestComparisonExporter
from backtest.backtest_engine import BacktestEngine
from backtest.backtest_insights_engine import BacktestInsightsEngine
from backtest.backtest_insights_exporter import BacktestInsightsExporter
from backtest.equity_analytics_engine import EquityAnalyticsEngine
from backtest.historical_data_provider import HistoricalDataProvider
from backtest.parameter_sweep_engine import ParameterSweepEngine
from backtest.parameter_sweep_exporter import ParameterSweepExporter
from backtest.walk_forward_engine import WalkForwardEngine
from backtest.walk_forward_exporter import WalkForwardExporter
from backtest.backtest_report_exporter import BacktestReportExporter
from market.binance_market_data_provider import BinanceMarketDataProvider
from paper.paper_analytics_engine import PaperAnalyticsEngine
from paper.paper_cycle_manager import PaperCycleManager
from paper.paper_safety_engine import PaperSafetyEngine
from paper.paper_exchange import PaperExchange
from paper.paper_order_manager import PaperOrderManager
from paper.paper_portfolio_manager import PaperPortfolioManager
from paper.paper_recovery_manager import PaperRecoveryManager
from paper.paper_insights_engine import PaperInsightsEngine
from paper.paper_insights_exporter import PaperInsightsExporter
from paper.paper_report_exporter import PaperReportExporter
from paper.paper_trading_cli_renderer import PaperTradingCliRenderer
from paper.paper_trading_engine import PaperTradingEngine
from paper.extreme_signal_provider import EXTREME_MAX_HOLDING_SECONDS, ExtremeSignalMarketAnalyzer
from paper.hf_short_center_provider import HFShortCenterMarketAnalyzer
from paper.long_paper_run_workflow import LongPaperRunWorkflow

from app.app_logger import AppLogger
from app.bot_engine import BotEngine
from config.config_manager import ConfigManager
from health.health_check import HealthCheck
from notifications.notification_engine import NotificationEngine
from portfolio.portfolio_analytics import PortfolioAnalytics
from runner.bot_runner import BotRunner
from storage.database_manager import DatabaseManager
from strategy.profile_decision_engine import (
    SUPPORTED_RUNTIME_STRATEGY_PROFILES,
    StrategyProfileDecisionEngine,
)
from trading.fee_engine import FeeEngine
from analytics.center_confidence_diagnostics_engine import CenterConfidenceDiagnosticsEngine
from analytics.center_confidence_rule_sim_engine import CenterConfidenceRuleSimulationEngine
from analytics.break_even_rebase_sim_engine import BreakEvenRebaseSimulationEngine
from analytics.combined_entry_rule_sim_engine import CombinedEntryRuleSimulationEngine
from analytics.confidence_diagnostics_engine import ConfidenceDiagnosticsEngine
from analytics.data_source_check_engine import DataSourceCheckEngine
from analytics.decision_diagnostics_engine import DecisionDiagnosticsEngine
from analytics.direction_outcome_diagnostics_engine import DirectionOutcomeDiagnosticsEngine
from analytics.entry_confirmation_diagnostics_engine import EntryConfirmationDiagnosticsEngine
from analytics.entry_zone_diagnostics_engine import EntryZoneDiagnosticsEngine
from analytics.entry_zone_debug_report import EntryZoneDebugReportBuilder
from analytics.entry_threshold_sensitivity_engine import EntryThresholdSensitivityEngine
from analytics.exit_risk_diagnostics_engine import ExitRiskDiagnosticsEngine
from analytics.exit_rule_optimizer_engine import ExitRuleOptimizerEngine
from analytics.exit_rule_sim_engine import ExitRuleSimulationEngine
from analytics.exit_tolerance_sim_engine import ExitToleranceSimulationEngine
from analytics.extreme_late_entry_diagnostics_engine import ExtremeLateEntryDiagnosticsEngine
from analytics.extreme_market_discovery_engine import ExtremeMarketDiscoveryEngine
from analytics.extreme_paper_signal_diagnostics_engine import ExtremePaperSignalDiagnosticsEngine
from analytics.extreme_replay_engine import ExtremeReplayEngine
from analytics.extreme_replay_ranking_engine import ExtremeReplayRankingEngine
from analytics.extreme_signal_discovery_engine import ExtremeSignalDiscoveryEngine
from analytics.extreme_signal_leadtime_engine import ExtremeSignalLeadTimeEngine
from analytics.fee_model_report_engine import FeeModelReportEngine
from analytics.filter_pass_diagnostics_engine import FilterPassDiagnosticsEngine
from analytics.holding_horizon_diagnostics_engine import HoldingHorizonDiagnosticsEngine
from analytics.high_frequency_dataset_summary_engine import HighFrequencyDatasetSummaryEngine
from analytics.high_frequency_diagnostics_engine import HighFrequencyDiagnosticsEngine
from analytics.high_frequency_snapshot_collector import HighFrequencySnapshotCollector
from analytics.hf_collection_extreme_metrics import HFCollectionExtremeMetricsEngine
from analytics.hf_extreme_price import is_extreme_close_price
from analytics.hf_losing_cycle_diagnostics_engine import HFLosingCycleDiagnosticsEngine
from analytics.hf_micro_grid_guard_sweep_engine import HFMicroGridGuardSweepEngine
from analytics.hf_micro_grid_sim_engine import (
    HF_GRID_DEFAULT_LAYER_SIZE,
    HF_GRID_DEFAULT_GUARD_LOSS_THRESHOLD,
    HF_GRID_DEFAULT_GUARD_MIN_LAYERS,
    HF_GRID_DEFAULT_MAX_HOLDING_SECONDS,
    HF_GRID_DEFAULT_MAX_LAYERS,
    HF_GRID_DEFAULT_SCENARIO,
    HF_GRID_DEFAULT_TARGET_PERCENT,
    HFMicroGridSimulationEngine,
)
from analytics.hf_extreme_move_diagnostics_engine import HFExtremeMoveDiagnosticsEngine
from analytics.hf_profit_audit_engine import HFProfitAuditEngine
from analytics.hf_production_readiness_engine import HFProductionReadinessEngine
from analytics.hf_real_dry_run_engine import HFRealDryRunEngine
from analytics.hf_real_pilot_engine import HFRealPilotEngine, HFRealPilotSignalSnapshot
from analytics.hf_regime_filter_sim_engine import HFRegimeFilterSimulationEngine
from analytics.hf_run_regime_comparison_engine import HFRunRegimeComparisonEngine
from analytics.hf_velocity_filter_sim_engine import HFVelocityFilterSimulationEngine
from analytics.max_holding_sensitivity_engine import MaxHoldingSensitivityEngine
from analytics.market_session_diagnostics_engine import MarketSessionDiagnosticsEngine
from analytics.ml_baseline_trainer import MLBaselineTrainer
from analytics.ml_dataset_coverage_engine import MLDatasetCoverageEngine
from analytics.ml_dataset_exporter import MLDatasetExporter, SUPPORTED_DATASET_MODES
from analytics.ml_dataset_summary_engine import MLDatasetSummaryEngine
from analytics.micro_trend_sensitivity_engine import MicroTrendSensitivityEngine
from analytics.micro_cycle_sim_engine import (
    MICRO_CYCLE_SCENARIOS,
    MicroCycleSimulationEngine,
)
from analytics.micro_cycle_grid_search_engine import (
    MICRO_CYCLE_GRID_SCENARIOS,
    MicroCycleGridSearchEngine,
)
from analytics.order_book_diagnostics_engine import OrderBookDiagnosticsEngine
from analytics.order_book_rule_sim_engine import OrderBookRuleSimulationEngine
from analytics.paper_open_cycle_diagnostics_engine import PaperOpenCycleDiagnosticsEngine
from analytics.paper_outlier_validation_engine import PaperOutlierValidationEngine
from analytics.paper_profit_concentration_engine import PaperProfitConcentrationEngine
from analytics.partial_target_diagnostics_engine import PartialTargetDiagnosticsEngine
from analytics.post_entry_path_diagnostics_engine import PostEntryPathDiagnosticsEngine
from analytics.profile_comparison_diagnostics_engine import ProfileComparisonDiagnosticsEngine
from analytics.profile_performance_summary_engine import ProfilePerformanceSummaryEngine
from analytics.range_shift_diagnostics_engine import RangeShiftDiagnosticsEngine
from analytics.risk_diagnostics_engine import RiskDiagnosticsEngine
from analytics.risk_profitability_diagnostics_engine import RiskProfitabilityDiagnosticsEngine
from analytics.session_filter_sim_engine import SessionFilterSimulationEngine
from analytics.statistics_engine import StatisticsEngine
from analytics.strategy_profile_sim_engine import (
    SUPPORTED_STRATEGY_PROFILES,
    StrategyProfileSimulationEngine,
)
from analytics.strategy_tuning_report_engine import StrategyTuningReportEngine
from analytics.strategy_validation_engine import StrategyValidationEngine
from analytics.target_rebase_diagnostics_engine import TargetRebaseDiagnosticsEngine
from analytics.target_profit_sensitivity_engine import TargetProfitSensitivityEngine
from analytics.target_resolution_diagnostics_engine import TargetResolutionDiagnosticsEngine
from analytics.trend_alignment_diagnostics_engine import TrendAlignmentDiagnosticsEngine
from analytics.trend_strength_diagnostics_engine import TrendStrengthDiagnosticsEngine
from analytics.validation_summary_engine import ValidationSummaryEngine
from app.text_encoding import clean_display_text


def configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _parse_float_list(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _positive_decimal_float(raw: str) -> float:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError("value must be a positive decimal number.") from exc
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0.")
    return float(value)


def _decimal_float(raw: str) -> float:
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError("value must be a decimal number.") from exc
    if not value.is_finite():
        raise argparse.ArgumentTypeError("value must be finite.")
    return float(value)


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer.") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0.")
    return value


def build_context():
    config = ConfigManager().config
    logger = AppLogger(config).configure()
    database = DatabaseManager(config.database_path)
    return config, logger, database


def _profile_decision_engine(config, profile: str):
    if profile == "strict_current":
        return None
    return StrategyProfileDecisionEngine(config, profile)


def _apply_profile_to_bot(bot: BotEngine, profile: str) -> BotEngine:
    if profile != "strict_current":
        bot.decision_engine = StrategyProfileDecisionEngine(bot.config, profile)
    if profile == "mean_reversion_hf_micro_v1" and not isinstance(bot.market_analyzer, HFShortCenterMarketAnalyzer):
        bot.market_analyzer = HFShortCenterMarketAnalyzer(bot.market_analyzer)
    if profile == "extreme_strategy_v1" and not isinstance(bot.market_analyzer, ExtremeSignalMarketAnalyzer):
        bot.market_analyzer = ExtremeSignalMarketAnalyzer(bot.market_analyzer)
    return bot


def _ensure_profile_allowed_for_paper(config, profile: str) -> None:
    if profile != "strict_current" and config.mode.upper() == "REAL":
        raise ValueError("Experimental strategy profiles are disabled in REAL mode.")


def _build_decision_debug_callback(profile: str):
    counter = {"count": 0}

    def callback(item: dict) -> None:
        counter["count"] += 1
        market_state = item.get("market_state")
        market_debug = item.get("market_debug_info") or {}
        cache_hits = market_debug.get("cache_hits", "N/A")
        cache_misses = market_debug.get("cache_misses", "N/A")
        last_fetch = market_debug.get("last_fetch_timestamp") or "N/A"
        fallback_error = market_debug.get("fallback_error") or ""
        fallback_part = f" | fallback_error={fallback_error}" if fallback_error else ""
        if market_state is None:
            print(
                "[decision-debug] "
                f"index={item['index']} | "
                f"work_position={item['work_position']:.4f} | "
                f"profile={profile} | "
                f"action={item['action']} | "
                f"reason={item['reason']} | "
                f"risk_allowed={item['risk_allowed']} | "
                f"risk_reason={item['risk_reason']}"
            )
            return

        print(
            "[decision-debug] "
            f"index={item['index']} | "
            f"timestamp={market_state.created_at.isoformat()} | "
            f"price={market_state.price:.8f} | "
            f"bid={market_state.bid:.8f} | "
            f"ask={market_state.ask:.8f} | "
            f"spread={market_state.spread:.8f} | "
            f"work_position={market_state.work_position:.4f} | "
            f"short_position={market_state.short_position:.4f} | "
            f"long_position={market_state.long_position:.4f} | "
            f"micro_trend={market_state.micro_trend} | "
            f"order_book_pressure={market_state.order_book_pressure} | "
            f"data_source={item.get('data_source', 'UNKNOWN')} | "
            f"cache_hits={cache_hits} | "
            f"cache_misses={cache_misses} | "
            f"last_fetch={last_fetch} | "
            f"profile={profile} | "
            f"action={item['action']} | "
            f"reason={item['reason']} | "
            f"risk_allowed={item['risk_allowed']} | "
            f"risk_reason={item['risk_reason']}"
            f"{fallback_part}"
        )

    return callback, counter


def _build_risk_profitability_debug_callback(config, database):
    from audit.audit_engine import AuditEngine

    counter = {"count": 0}
    diagnostics = RiskProfitabilityDiagnosticsEngine(config)
    audit_engine = AuditEngine(database)

    def callback(item: dict) -> None:
        counter["count"] += 1
        decision = item["decision"]
        risk = item["risk"]
        market_state = item["market_state"]
        portfolio = item["portfolio"]
        detail = diagnostics.build_detail(
            action=decision.action,
            current_price=market_state.price,
            budget_total_value=portfolio.total_value,
            reason=risk.reason,
        )
        audit_engine.audit_decision(market_state, decision, risk)
        _print_risk_profitability_detail(detail, prefix=f"[risk-debug] index={item['index']} | ")

    return callback, counter


def _build_entry_zone_debug_callback(config):
    builder = EntryZoneDebugReportBuilder(config)

    def callback(item: dict) -> None:
        debug_item = builder.add(item)
        print(
            "[entry-zone-debug] "
            f"index={debug_item.index} | "
            f"timestamp={debug_item.timestamp} | "
            f"bid={debug_item.bid:.8f} | "
            f"ask={debug_item.ask:.8f} | "
            f"mid={debug_item.mid_price:.8f} | "
            f"spread={debug_item.spread:.8f} | "
            f"reference_price={debug_item.reference_price:.8f} | "
            f"deviation={debug_item.deviation_from_mean:.8f} "
            f"({debug_item.deviation_from_mean_percent:.5f}%) | "
            f"work_position={debug_item.work_position:.4f} | "
            f"buy_zone_threshold<={debug_item.buy_zone_threshold:.4f} | "
            f"sell_zone_threshold>={debug_item.sell_zone_threshold:.4f} | "
            f"buy_zone_active={debug_item.buy_zone_active} | "
            f"sell_zone_active={debug_item.sell_zone_active} | "
            f"micro_trend={debug_item.micro_trend} | "
            f"micro_trend_result={debug_item.micro_trend_result} | "
            f"action={debug_item.action} | "
            f"candidate_produced={debug_item.candidate_produced} | "
            f"risk_check_evaluated={debug_item.risk_check_evaluated} | "
            f"order_attempted={debug_item.order_attempted} | "
            f"data_source={debug_item.data_source} | "
            f"reason={debug_item.reason} | "
            f"risk_reason={debug_item.risk_reason}"
        )

    return callback, builder


def _build_close_debug_callback():
    counter = {"count": 0}

    def callback(item: dict) -> None:
        counter["count"] += 1
        print(
            "[close-debug] "
            f"index={item['index']} | "
            f"db_id={item['db_id']} | "
            f"cycle_id={item['cycle_id']} | "
            f"profile={item['strategy_profile']} | "
            f"direction={item['direction']} | "
            f"current_price={item['current_price']:.8f} | "
            f"target_price={item['target_price']:.8f} | "
            f"current_price_raw={item.get('current_price_raw', item['current_price']):.8f} | "
            f"target_price_raw={item.get('target_price_raw', item['target_price']):.8f} | "
            f"current_price_rounded={item.get('current_price_rounded', item['current_price']):.8f} | "
            f"target_price_rounded={item.get('target_price_rounded', item['target_price']):.8f} | "
            f"close_rounding_decimals={item.get('close_rounding_decimals', 'N/A')} | "
            f"close_epsilon={item.get('close_epsilon', 0.0):.8f} | "
            f"effective_buy_close_price={item.get('effective_buy_close_price', item['current_price']):.8f} | "
            f"effective_sell_close_price={item.get('effective_sell_close_price', item['current_price']):.8f} | "
            f"close_tolerance={item.get('close_tolerance', 0.0):.8f} | "
            f"close_rounding_digits={item.get('close_rounding_digits', 'N/A')} | "
            f"close_condition_met={item['close_condition_met']} | "
            f"close_attempted={item['close_attempted']} | "
            f"close_result={item['close_result']} | "
            f"reason={item['reason']}"
        )

    return callback, counter


def _print_entry_zone_debug_summary(builder: EntryZoneDebugReportBuilder) -> None:
    summary = builder.summary()
    print("--- Entry Zone Debug Summary ---")
    print(f"Total iterations: {summary.total_iterations}")
    print(f"BUY zone active count: {summary.buy_zone_active_count}")
    print(f"SELL zone active count: {summary.sell_zone_active_count}")
    print(f"No-zone count: {summary.no_zone_count}")
    print(f"Blocked by micro_trend count: {summary.blocked_by_micro_trend_count}")
    print(f"Candidates produced count: {summary.candidates_produced_count}")
    print(f"Risk checks evaluated count: {summary.risk_checks_evaluated_count}")
    print(f"Orders attempted count: {summary.orders_attempted_count}")


def _print_risk_profitability_detail(detail, prefix: str = "") -> None:
    header = (
        f"{prefix}action={detail.action} | "
        f"current_price={detail.current_price:.8f} | "
        f"target_price={detail.target_price:.8f} | "
        f"allowed={detail.allowed}"
    )
    if detail.timestamp:
        header = f"{detail.timestamp} | {header}"
    print(header)
    if detail.decision_reason:
        print(f"  decision reason: {detail.decision_reason}")
    print(f"  trade_size: {detail.trade_size:.8f}")
    print(f"  quantity before rounding: {detail.quantity_before_rounding:.8f}")
    print(f"  quantity after rounding: {detail.quantity_after_rounding:.8f}")
    print(f"  open notional before rounding: {detail.open_notional_before_rounding:.8f}")
    print(f"  open notional after rounding: {detail.open_notional_after_rounding:.8f}")
    print(f"  rounding impact: {detail.rounding_impact:.8f}")
    print(f"  gross_profit: {detail.gross_profit:.8f}")
    print(f"  estimated fees: {detail.estimated_fees:.8f}")
    print(f"  net_profit: {detail.net_profit:.8f}")
    print(f"  min_notional: {detail.min_notional:.8f}")
    print(f"  reason if blocked: {detail.reason}")


def _load_current_paper_price(config, database) -> tuple[float, str, str]:
    try:
        return _load_binance_paper_price(config)
    except Exception:
        with database.connect() as conn:
            row = conn.execute(
                """
                SELECT timestamp, price
                FROM market_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()
        if row:
            return float(row[1]), "LATEST_MARKET_SNAPSHOT", str(row[0])
        return 1.0, "DEFAULT_1_0", datetime.now().isoformat()


def _load_binance_paper_price(config) -> tuple[float, str, str]:
    bid_ask = BinanceMarketDataProvider(base_url=config.binance_base_url).get_bid_ask(config.symbol)
    return bid_ask.mid_price, "BINANCE", datetime.now().isoformat()


def _price_age_seconds(timestamp: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return None
    now = datetime.now(tz=parsed.tzinfo) if parsed.tzinfo else datetime.now()
    return max(0.0, (now - parsed).total_seconds())


def _is_stale_price_source(source: str, age_seconds: float | None) -> bool:
    if source == "BINANCE":
        return False
    if source in {"LATEST_MARKET_SNAPSHOT", "DEFAULT_1_0"}:
        return True
    return age_seconds is None or age_seconds > 60.0


def _print_open_cycles_summary(report) -> None:
    print("--- Open Paper Cycles ---")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Open cycles count: {report.open_cycles_count}")
    nearest = report.nearest_to_target
    if nearest is None:
        print("Nearest cycle to target: N/A")
        return
    print(
        "Nearest cycle to target: "
        f"db_id={nearest.db_id} cycle_id={nearest.cycle_id} profile={nearest.profile} "
        f"direction={nearest.direction} distance={nearest.distance_to_target:.8f} "
        f"({nearest.distance_to_target_percent:.5f}%)"
    )
    print(f"Close condition met: {'yes' if nearest.close_condition_met else 'no'}")
    print(f"Reason: {nearest.reason_not_closed}")


def command_run(args) -> None:
    config, logger, database = build_context()
    logger.info("CLI run command started")

    bot = BotEngine()
    runner = BotRunner(
        bot=bot,
        interval_seconds=args.interval or config.runner_interval_seconds,
        max_iterations=args.iterations or config.max_runner_iterations,
    )
    result = runner.run()

    print(
        f"Runner Р·Р°РІРµСЂС€РµРЅРѕ. Р†С‚РµСЂР°С†С–Р№: {result.iterations_completed}. "
        f"Р—СѓРїРёРЅРµРЅРѕ РїРѕ Р»С–РјС–С‚Сѓ: {result.stopped_by_limit}"
    )


def command_health(args) -> None:
    config, logger, database = build_context()
    report = HealthCheck(config=config, database=database).run()
    logger.info("CLI health command executed: ok=%s", report.ok)

    print("=== Health Check ===")
    for item in report.items:
        status = "OK" if item.ok else "FAIL"
        print(f"[{status}] {item.name}: {item.message}")


def command_data_source_check(args) -> None:
    config, logger, _database = build_context()
    report = DataSourceCheckEngine(config).build_report()
    logger.info(
        "CLI data-source-check executed: source=%s binance_ok=%s",
        report.source,
        report.binance_ok,
    )

    print("=== Data Source Check ===")
    print(f"Current mode: {report.mode}")
    print(f"use_real_market_data: {report.use_real_market_data}")
    print(f"Binance base URL: {report.binance_base_url}")
    print(f"Symbol: {report.symbol}")
    print(f"Binance health-check OK: {report.binance_ok}")
    print(f"Last price: {report.last_price if report.last_price is not None else 'N/A'}")
    print(f"Timestamp: {report.timestamp or 'N/A'}")
    print(f"Source: {report.source}")
    print("--- Workflow sources ---")
    print(f"Backtest: {report.backtest_source}")
    print(f"Runner: {report.runner_source}")
    print(f"Long Paper Run: {report.long_paper_run_source}")
    if report.error_message:
        print(f"Error: {report.error_message}")


def command_migrate(args) -> None:
    _config, logger, database = build_context()
    applied = database.run_migrations()
    logger.info("CLI migrate command executed. Applied: %s", applied)

    if not applied:
        print("РњС–РіСЂР°С†С–С— РЅРµ РїРѕС‚СЂС–Р±РЅС–. Р‘Р°Р·Р° РІР¶Рµ Р°РєС‚СѓР°Р»СЊРЅР°.")
        return

    print("Р—Р°СЃС‚РѕСЃРѕРІР°РЅРѕ РјС–РіСЂР°С†С–С—:")
    for item in applied:
        print(f"- {item}")


def command_stats(args) -> None:
    _config, _logger, database = build_context()
    statistics = StatisticsEngine(database).build_summary()
    portfolio = PortfolioAnalytics(database).calculate_stats(
        current_portfolio_value=database.calculate_net_deposits() + database.sum_realized_profit()
    )

    print("=== Statistics ===")
    print(f"Р¦РёРєР»С–РІ СѓСЃСЊРѕРіРѕ: {statistics.cycle_stats.total_cycles}")
    print(f"Р—Р°РєСЂРёС‚РёС… С†РёРєР»С–РІ: {statistics.cycle_stats.closed_cycles}")
    print(f"РђРєС‚РёРІРЅРёС… С†РёРєР»С–РІ: {statistics.cycle_stats.active_cycles}")
    print(f"Win rate: {statistics.cycle_stats.win_rate * 100:.2f}%")
    print(f"Р РµР°Р»С–Р·РѕРІР°РЅРёР№ РїСЂРёР±СѓС‚РѕРє: {statistics.cycle_stats.realized_profit:.8f}")
    print(f"РЎРёРіРЅР°Р»С–РІ СѓСЃСЊРѕРіРѕ: {statistics.signal_stats.total_signals}")
    print(f"BUY: {statistics.signal_stats.buy_signals}")
    print(f"SELL: {statistics.signal_stats.sell_signals}")
    print(f"WAIT: {statistics.signal_stats.wait_signals}")
    print(f"SAFE_WAIT: {statistics.signal_stats.safe_wait_signals}")
    print("--- Portfolio ---")
    print(f"Total deposits: {portfolio.total_deposits:.2f}")
    print(f"Net deposits: {portfolio.net_deposits:.2f}")
    print(f"ROI: {portfolio.roi * 100:.4f}%")


def command_strategy_report(args) -> None:
    _config, _logger, database = build_context()
    summary = StrategyValidationEngine(database).build_summary()

    print("=== Strategy Validation Report ===")
    if summary.total_signals == 0:
        print("No strategy data available.")
        return

    print(f"Signals generated: {summary.total_signals}")
    print(f"BUY signals: {summary.buy_signals}")
    print(f"SELL signals: {summary.sell_signals}")
    print(f"Avg confidence: {summary.average_confidence * 100:.2f}%")
    print(f"Avg spread: {summary.average_spread:.8f}")
    print(f"Avg volatility: {summary.average_volatility:.8f}")
    print("Market regimes:")
    if summary.market_regime_distribution:
        for regime, count in summary.market_regime_distribution.items():
            print(f"- {regime}: {count}")
    else:
        print("- No market snapshots yet.")


def command_strategy_tuning_report(args) -> None:
    _config, _logger, database = build_context()
    report = StrategyTuningReportEngine(database).build_report(top=args.top)

    print("=== Strategy Tuning Report ===")
    print("Simulation only. DecisionEngine, RiskManager, config, and trades are unchanged.")
    if report.total_signals == 0:
        print("No tuning data available.")
        return

    print(f"Total signals: {report.total_signals}")
    for item in report.thresholds:
        print(f"--- min_confidence >= {item.threshold:.1f} ---")
        print(f"Total passed: {item.total_passed}")
        print(f"Pass rate: {item.pass_rate * 100:.2f}%")
        print(f"BUY candidates: {item.buy_candidates}")
        print(f"SELL candidates: {item.sell_candidates}")
        print(f"WAIT still blocked: {item.wait_still_blocked}")
        print("Top remaining reasons:")
        _print_reason_rows(item.top_remaining_reasons)


def command_decision_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    summary = DecisionDiagnosticsEngine(database).build_summary(top=args.top)

    print("=== Decision Diagnostics ===")
    if summary.total_decisions == 0:
        print("No decision diagnostics data available.")
        return

    print(f"Total decisions/signals: {summary.total_decisions}")
    print(f"BUY count: {summary.buy_count}")
    print(f"SELL count: {summary.sell_count}")
    print(f"WAIT count: {summary.wait_count}")
    print(f"Risk blocked: {summary.risk_blocked_count}")
    print("Top WAIT reasons:")
    _print_reason_rows(summary.top_wait_reasons)
    print("Top BUY reasons:")
    _print_reason_rows(summary.top_buy_reasons)
    print("Top SELL reasons:")
    _print_reason_rows(summary.top_sell_reasons)
    print("Confidence distribution:")
    if summary.confidence_distribution:
        for confidence, count in summary.confidence_distribution.items():
            print(f"- {confidence}: {count}")
    else:
        print("- No confidence data.")


def command_risk_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    summary = RiskDiagnosticsEngine(database).build_summary(top=args.top, latest=args.latest)

    print("=== Risk Diagnostics ===")
    if summary.total_audited_decisions == 0:
        print("No risk diagnostics data available.")
        return

    print(f"Total audited decisions: {summary.total_audited_decisions}")
    print(f"Allowed count: {summary.allowed_count}")
    print(f"Blocked count: {summary.blocked_count}")
    print(f"Blocked rate: {summary.blocked_rate * 100:.2f}%")
    print("Top risk reasons:")
    _print_reason_rows(summary.top_risk_reasons)
    print("Action distribution for blocked decisions:")
    if summary.blocked_action_distribution:
        for action, count in summary.blocked_action_distribution.items():
            print(f"- {action}: {count}")
    else:
        print("- No blocked decisions.")
    print("Latest blocked decisions:")
    if summary.latest_blocked_decisions:
        for item in summary.latest_blocked_decisions:
            print(
                f"- {item.timestamp} | {item.decision} | "
                f"{item.risk_reason} | {item.reason}"
            )
    else:
        print("- No blocked decisions.")


def command_risk_profitability_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = RiskProfitabilityDiagnosticsEngine(config, database).build_report(limit=args.limit)

    print("=== Risk Profitability Diagnostics ===")
    if not report.details:
        print("No blocked BUY/SELL profitability decisions found.")
        return

    if report.estimated_from_config:
        print(
            "Note: historical breakdown uses audit price and current config initial portfolio "
            "to estimate trade_size."
        )
    for detail in report.details:
        _print_risk_profitability_detail(detail)
        print("-" * 60)


def command_fee_model_report(args) -> None:
    config, _logger, _database = build_context()
    report = FeeModelReportEngine(config).build_report(trade_size=args.trade_size)

    print("=== Fee Model Report ===")
    print(f"Configured maker fee: {report.configured_maker_fee:.6f} ({report.configured_maker_fee * 100:.4f}%)")
    print(f"Configured taker fee: {report.configured_taker_fee:.6f} ({report.configured_taker_fee * 100:.4f}%)")
    print(f"Effective maker fee: {report.effective_maker_fee:.6f} ({report.effective_maker_fee * 100:.4f}%)")
    print(f"Effective taker fee: {report.effective_taker_fee:.6f} ({report.effective_taker_fee * 100:.4f}%)")
    print(f"Effective fee source: {report.effective_fee_source}")
    print(f"Effective fee note: {report.effective_fee_note}")
    print("")
    print("Backtest fee model:")
    print(report.backtest_model)
    print("Paper fee model:")
    print(report.paper_model)
    print("Risk profitability fee model:")
    print(report.risk_profitability_model)
    print("")
    print(f"Example calculation for trade_size={args.trade_size:g}:")
    for scenario in report.scenarios:
        print("")
        print(f"{scenario.name}:")
        print(f"  open fee rate: {scenario.open_fee_rate:.6f}")
        print(f"  close fee rate: {scenario.close_fee_rate:.6f}")
        print(f"  open fee: {scenario.open_fee:.8f}")
        print(f"  close fee: {scenario.close_fee:.8f}")
        print(f"  total fee: {scenario.total_fee:.8f}")
        print(f"  gross profit: {scenario.gross_profit:.8f}")
        print(f"  net profit: {scenario.net_profit:.8f}")
    print("")
    print(f"Risk example estimated_fees: {report.risk_example_estimated_fees:.8f}")
    print("Observed fee check:")
    print(report.observed_fee_rate_interpretation)
    print("")
    print("Fee model source:")
    for item in report.fee_model_source:
        print(f"- {item}")
    print("")
    print(f"Fee model consistency: {report.fee_model_consistency}")
    print("Notes:")
    for item in report.notes:
        print(f"- {item}")


def command_confidence_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    summary = ConfidenceDiagnosticsEngine(database).build_summary(top=args.top)

    print("=== Confidence Diagnostics ===")
    if summary.total_decisions == 0:
        print("No confidence diagnostics data available.")
        return

    print(f"Total decisions/signals: {summary.total_decisions}")
    print(f"Average confidence: {summary.average_confidence:.4f}")
    print(f"Min confidence: {summary.min_confidence:.4f}")
    print(f"Max confidence: {summary.max_confidence:.4f}")
    print(f"Median confidence: {summary.median_confidence:.4f}")
    print("Confidence buckets:")
    for bucket, count in summary.confidence_buckets.items():
        print(f"- {bucket}: {count}")
    print("Top WAIT reasons:")
    _print_reason_rows(summary.top_wait_reasons)
    print("Center distance statistics:")
    print(f"- Average: {summary.center_distance.average:.4f}")
    print(f"- Min: {summary.center_distance.minimum:.4f}")
    print(f"- Max: {summary.center_distance.maximum:.4f}")
    print("Market regimes:")
    if summary.market_regime_distribution:
        for regime, count in summary.market_regime_distribution.items():
            print(f"- {regime}: {count}")
    else:
        print("- No market snapshots yet.")


def command_entry_zone_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    summary = EntryZoneDiagnosticsEngine(database).build_summary()

    print("=== Entry Zone Diagnostics ===")
    if summary.total_snapshots == 0:
        print("No entry zone data available.")
        return

    print(f"Total snapshots: {summary.total_snapshots}")
    print(f"Average work_position: {summary.average_work_position:.4f}")
    print(f"Min work_position: {summary.min_work_position:.4f}")
    print(f"Max work_position: {summary.max_work_position:.4f}")
    print(f"Median work_position: {summary.median_work_position:.4f}")
    print("Position buckets:")
    for bucket, count in summary.buckets.items():
        print(f"- {bucket}: {count}")
    print(f"Potential BUY zone count: {summary.potential_buy_zone_count}")
    print(f"Potential SELL zone count: {summary.potential_sell_zone_count}")
    print(f"Center zone count: {summary.center_zone_count}")
    print(f"Average spread: {summary.average_spread:.8f}")
    print(f"Average market health score: {summary.average_market_health_score:.4f}")
    print("Market regimes:")
    if summary.market_regime_distribution:
        for regime, count in summary.market_regime_distribution.items():
            print(f"- {regime}: {count}")
    else:
        print("- No market snapshots yet.")


def command_filter_pass_diagnostics(args) -> None:
    config, _logger, database = build_context()
    summary = FilterPassDiagnosticsEngine(database, config).build_summary(latest=args.latest)

    print("=== Filter Pass Diagnostics ===")
    if summary.total_entry_zone_snapshots == 0:
        print("No filter pass diagnostics data available.")
        return

    if summary.warning:
        print(f"WARNING: {summary.warning}")
    print(f"Total entry zone snapshots: {summary.total_entry_zone_snapshots}")
    print(f"BUY zone snapshots: {summary.buy_zone_snapshots}")
    print(f"SELL zone snapshots: {summary.sell_zone_snapshots}")
    print("Filter pass rates:")
    for item in summary.filters:
        print(
            f"- {item.name}: passed={item.passed} failed={item.failed} "
            f"unknown={item.unknown} pass_rate={item.pass_rate * 100:.2f}% "
            f"| threshold: {item.threshold}"
        )
    print("Top blocking filters:")
    if summary.top_blocking_filters:
        for name, failed in summary.top_blocking_filters:
            print(f"- {name}: {failed}")
    else:
        print("- No blocking filters detected.")
    print("Latest blocked entry-zone snapshots:")
    if summary.latest_blocked_snapshots:
        for item in summary.latest_blocked_snapshots:
            filters = ", ".join(item.failed_filters) if item.failed_filters else "none"
            print(
                f"- {item.timestamp} | {item.zone} | "
                f"work_position={item.work_position:.4f} | failed={filters}"
            )
    else:
        print("- No blocked entry-zone snapshots.")


def command_order_book_diagnostics(args) -> None:
    config, _logger, database = build_context()
    summary = OrderBookDiagnosticsEngine(database, config).build_summary(latest=args.latest)

    print("=== Order Book Diagnostics ===")
    if summary.total_snapshots == 0:
        print("No order book diagnostics data available.")
        return

    print(f"Total snapshots: {summary.total_snapshots}")
    print(f"Entry-zone snapshots: {summary.entry_zone_snapshots}")
    print("Order book pressure distribution:")
    for pressure, count in summary.order_book_pressure_distribution.items():
        print(f"- {pressure}: {count}")
    print("BUY-zone pressure distribution:")
    for pressure, count in summary.buy_zone_distribution.items():
        print(f"- {pressure}: {count}")
    print("SELL-zone pressure distribution:")
    for pressure, count in summary.sell_zone_distribution.items():
        print(f"- {pressure}: {count}")
    print(f"Average order_book_imbalance: {summary.average_order_book_imbalance:.6f}")
    print(f"Min order_book_imbalance: {summary.min_order_book_imbalance:.6f}")
    print(f"Max order_book_imbalance: {summary.max_order_book_imbalance:.6f}")
    print("Latest entry-zone snapshots:")
    if summary.latest_entry_zone_snapshots:
        for item in summary.latest_entry_zone_snapshots:
            print(
                f"- {item.timestamp} | {item.direction_candidate} | "
                f"work_position={item.work_position:.4f} | "
                f"order_book_pressure={item.order_book_pressure} | "
                f"order_book_imbalance={item.order_book_imbalance:.6f} | "
                f"micro_trend={item.micro_trend} | "
                f"center_confidence={item.center_confidence}"
            )
    else:
        print("- No entry-zone snapshots.")


def command_order_book_rule_sim(args) -> None:
    config, _logger, database = build_context()
    report = OrderBookRuleSimulationEngine(database, config).build_report()

    print("=== Order Book Rule Simulation ===")
    print("Simulation only. DecisionEngine, RiskManager, config, and trades are unchanged.")
    if not report.profiles or report.profiles[0].total_entry_zone_samples == 0:
        print("No entry-zone samples available.")
        return

    for profile in report.profiles:
        print(f"--- {profile.name} ---")
        print(f"Total entry-zone samples: {profile.total_entry_zone_samples}")
        print(f"BUY candidates: {profile.buy_candidates}")
        print(f"SELL candidates: {profile.sell_candidates}")
        print(f"Pass count: {profile.pass_count}")
        print(f"Pass rate: {profile.pass_rate * 100:.2f}%")
        print("Remaining blocking filters:")
        if profile.remaining_blocking_filters:
            for name, count in profile.remaining_blocking_filters:
                print(f"- {name}: {count}")
        else:
            print("- None")


def command_center_confidence_diagnostics(args) -> None:
    config, _logger, database = build_context()
    summary = CenterConfidenceDiagnosticsEngine(database, config).build_summary(latest=args.latest)

    print("=== Center Confidence Diagnostics ===")
    if summary.total_snapshots == 0:
        print("No center confidence diagnostics data available.")
        return

    print(f"Total snapshots: {summary.total_snapshots}")
    print("Confidence distribution:")
    for label, count in summary.confidence_distribution.items():
        print(f"- {label}: {count}")
    print("Entry-zone confidence distribution:")
    for label, count in summary.entry_zone_confidence_distribution.items():
        print(f"- {label}: {count}")
    print("Center-zone confidence distribution:")
    for label, count in summary.center_zone_confidence_distribution.items():
        print(f"- {label}: {count}")
    print("Metric stats:")
    _print_metric_stats("work_position", summary.work_position_stats)
    _print_metric_stats("work_center", summary.work_center_stats)
    _print_metric_stats("short_center", summary.short_center_stats)
    _print_metric_stats("long_center", summary.long_center_stats)
    print("Center alignment distribution:")
    if summary.center_alignment_distribution:
        for label, count in summary.center_alignment_distribution.items():
            print(f"- {label}: {count}")
    else:
        print("- No alignment data.")
    print("Center distances:")
    _print_metric_stats("abs(work_center - short_center)", summary.work_short_distance_stats)
    _print_metric_stats("abs(work_center - long_center)", summary.work_long_distance_stats)
    _print_metric_stats("abs(short_center - long_center)", summary.short_long_distance_stats)
    print("Latest LOW confidence snapshots:")
    if summary.latest_low_confidence_snapshots:
        for item in summary.latest_low_confidence_snapshots:
            print(
                f"- {item.timestamp} | "
                f"work_center={item.work_center:.8f} | "
                f"short_center={item.short_center:.8f} | "
                f"long_center={item.long_center:.8f} | "
                f"alignment={item.center_alignment} | "
                f"work_position={item.work_position:.4f} | "
                f"regime={item.market_regime} | "
                f"spread={item.spread:.8f} | "
                f"order_book_pressure={item.order_book_pressure}"
            )
    else:
        print("- No LOW confidence snapshots.")


def command_center_confidence_rule_sim(args) -> None:
    config, _logger, database = build_context()
    report = CenterConfidenceRuleSimulationEngine(database, config).build_report(latest=args.latest)

    print("=== Center Confidence Rule Simulation ===")
    print("Simulation only. MarketAnalyzer, DecisionEngine, RiskManager, config, and trades are unchanged.")
    if not report.profiles or report.profiles[0].total_entry_zone_samples == 0:
        print("No entry-zone samples available.")
        return

    for profile in report.profiles:
        print(f"--- {profile.name} ---")
        print(f"Total entry-zone samples: {profile.total_entry_zone_samples}")
        print(f"BUY candidates: {profile.buy_candidates}")
        print(f"SELL candidates: {profile.sell_candidates}")
        print(f"Pass count: {profile.pass_count}")
        print(f"Pass rate: {profile.pass_rate * 100:.2f}%")
        print("Remaining blocking filters:")
        if profile.remaining_blocking_filters:
            for name, count in profile.remaining_blocking_filters:
                print(f"- {name}: {count}")
        else:
            print("- None")
        print("Latest passed samples:")
        if profile.latest_passed_samples:
            for item in profile.latest_passed_samples:
                print(
                    f"- {item.timestamp} | {item.zone} | "
                    f"work_position={item.work_position:.4f} | "
                    f"center_confidence={item.center_confidence} | "
                    f"work_short_distance={item.work_short_distance:.8f} | "
                    f"work_long_distance={item.work_long_distance:.8f} | "
                    f"short_long_distance={item.short_long_distance:.8f} | "
                    f"pressure={item.order_book_pressure} | "
                    f"micro_trend={item.micro_trend}"
                )
        else:
            print("- No passed samples.")


def command_combined_entry_rule_sim(args) -> None:
    config, _logger, database = build_context()
    report = CombinedEntryRuleSimulationEngine(database, config).build_report(latest=args.latest)

    print("=== Combined Entry Rule Simulation ===")
    print("Simulation only. MarketAnalyzer, DecisionEngine, RiskManager, config, and trades are unchanged.")
    if not report.profiles or report.profiles[0].total_entry_zone_samples == 0:
        print("No entry-zone samples available.")
        return

    for profile in report.profiles:
        print(f"--- {profile.name} ---")
        print(f"Total entry-zone samples: {profile.total_entry_zone_samples}")
        print(f"BUY candidates: {profile.buy_candidates}")
        print(f"SELL candidates: {profile.sell_candidates}")
        print(f"Pass count: {profile.pass_count}")
        print(f"Pass rate: {profile.pass_rate * 100:.2f}%")
        print("Remaining blocking filters:")
        if profile.remaining_blocking_filters:
            for name, count in profile.remaining_blocking_filters:
                print(f"- {name}: {count}")
        else:
            print("- None")
        print("Latest passed samples:")
        if profile.latest_passed_samples:
            for item in profile.latest_passed_samples:
                print(
                    f"- {item.timestamp} | {item.zone} | "
                    f"work_position={item.work_position:.4f} | "
                    f"center_confidence={item.center_confidence} | "
                    f"order_book_pressure={item.order_book_pressure} | "
                    f"micro_trend={item.micro_trend} | "
                    f"work_short_distance={item.work_short_distance:.8f} | "
                    f"work_long_distance={item.work_long_distance:.8f}"
                )
        else:
            print("- No passed samples.")


def command_strategy_profile_sim(args) -> None:
    _config, _logger, database = build_context()
    config = _config
    report = StrategyProfileSimulationEngine(database, config).build_report(
        profile=args.profile,
        latest=args.latest,
    )

    print("=== Strategy Profile Simulation ===")
    print("Simulation only. DecisionEngine, RiskManager, config, and trades are unchanged.")
    print(f"Configured strategy_profile: {config.strategy_profile}")
    print(f"Simulated profile: {report.profile}")
    if report.total_snapshots == 0:
        print("No strategy profile simulation data available.")
        return

    print(f"Total snapshots: {report.total_snapshots}")
    print(f"Total entry-zone samples: {report.total_entry_zone_samples}")
    print(f"Pass count: {report.pass_count}")
    print(f"Pass rate: {report.pass_rate * 100:.2f}%")
    print(f"BUY candidates: {report.buy_candidates}")
    print(f"SELL candidates: {report.sell_candidates}")
    print("Remaining blocking filters:")
    if report.remaining_blocking_filters:
        for name, count in report.remaining_blocking_filters:
            print(f"- {name}: {count}")
    else:
        print("- None")
    print("Latest candidates:")
    if report.latest_candidates:
        for item in report.latest_candidates:
            print(
                f"- {item.timestamp} | {item.direction} | "
                f"work_position={item.work_position:.4f} | "
                f"spread={item.spread:.8f} | "
                f"health={item.market_health_score:.2f} | "
                f"regime={item.market_regime} | "
                f"volatility={item.volatility_regime} | "
                f"micro_trend={item.micro_trend} | "
                f"center_confidence={item.center_confidence} | "
                f"order_book_pressure={item.order_book_pressure}"
            )
    else:
        print("- No candidates.")


def command_entry_threshold_sensitivity(args) -> None:
    config, _logger, database = build_context()
    report = EntryThresholdSensitivityEngine(database, config).build_report(profile=args.profile)

    print("=== Entry Threshold Sensitivity ===")
    print("Dry run only. Production strategy thresholds and trading behavior are unchanged.")
    print(f"Profile: {report.profile}")
    print(
        f"Configured thresholds: BUY <= {report.configured_buy_threshold:.1f} / "
        f"SELL >= {report.configured_sell_threshold:.1f}"
    )
    print(
        f"Effective fee rates: maker={report.fee_rates.maker:.6f} "
        f"taker={report.fee_rates.taker:.6f}"
    )
    print(f"Fee source: {report.fee_rates.source}")
    print("")

    if not report.variants or report.variants[0].total_samples == 0:
        print("No market snapshot data available.")
        return

    for item in report.variants:
        print(f"--- BUY <= {item.buy_threshold:.1f} / SELL >= {item.sell_threshold:.1f} ---")
        print(f"Total samples: {item.total_samples}")
        print(f"BUY zone count: {item.buy_zone_count}")
        print(f"SELL zone count: {item.sell_zone_count}")
        print(f"Candidate count: {item.candidate_count}")
        print(f"Micro trend pass count: {item.micro_trend_pass_count}")
        print(f"Risk profitability pass count: {item.risk_profitability_pass_count}")
        print(f"Min notional/order sizing pass count: {item.min_notional_pass_count}")
        print(f"Expected trade frequency estimate: {item.expected_trade_frequency * 100:.2f}%")
        if item.gross_profit_min is None:
            print("Estimated gross profit range: N/A")
            print("Estimated net profit range: N/A")
        else:
            print(
                "Estimated gross profit range: "
                f"{item.gross_profit_min:.8f} .. {item.gross_profit_max:.8f}"
            )
            print(
                "Estimated net profit range: "
                f"{item.net_profit_min:.8f} .. {item.net_profit_max:.8f}"
            )
        print("Remaining blockers:")
        if item.remaining_blockers:
            for name, count in item.remaining_blockers:
                print(f"- {name}: {count}")
        else:
            print("- None")


def command_micro_trend_sensitivity(args) -> None:
    config, _logger, database = build_context()
    report = MicroTrendSensitivityEngine(database, config).build_report(profile=args.profile)

    print("=== Micro Trend Sensitivity ===")
    print("Dry run only. Production strategy thresholds and trading behavior are unchanged.")
    print(f"Profile: {report.profile}")
    print(
        f"Effective fee rates: maker={report.fee_rates.maker:.6f} "
        f"taker={report.fee_rates.taker:.6f}"
    )
    print(f"Fee source: {report.fee_rates.source}")
    print("")

    if not report.results or report.results[0].total_samples == 0:
        print("No market snapshot data available.")
        return

    for item in report.results:
        print(f"--- BUY <= {item.buy_threshold:.1f} / SELL >= {item.sell_threshold:.1f} | {item.mode} ---")
        print(f"Total samples: {item.total_samples}")
        print(f"Zone count: {item.zone_count}")
        print(f"Candidates count: {item.candidates_count}")
        print(f"Candidate frequency: {item.candidate_frequency * 100:.2f}%")
        print(f"Risk profitability pass: {item.risk_profitability_pass_count}")
        if item.gross_profit_min is None:
            print("Estimated gross profit range: N/A")
            print("Estimated net profit range: N/A")
        else:
            print(
                "Estimated gross profit range: "
                f"{item.gross_profit_min:.8f} .. {item.gross_profit_max:.8f}"
            )
            print(
                "Estimated net profit range: "
                f"{item.net_profit_min:.8f} .. {item.net_profit_max:.8f}"
            )
        print("Micro trend distribution:")
        if item.micro_trend_distribution:
            for name, count in item.micro_trend_distribution:
                print(f"- {name}: {count}")
        else:
            print("- None")
        print("Remaining blockers:")
        if item.remaining_blockers:
            for name, count in item.remaining_blockers:
                print(f"- {name}: {count}")
        else:
            print("- None")

    print("--- Recommendation ---")
    if report.recommendation is None:
        print("No viable threshold/micro-trend combo found in saved samples.")
    else:
        recommendation = report.recommendation
        print(
            f"BUY <= {recommendation.buy_threshold:.1f} / "
            f"SELL >= {recommendation.sell_threshold:.1f} | "
            f"mode={recommendation.mode}"
        )
        print(f"Candidates: {recommendation.candidates_count}")
        print(f"Candidate frequency: {recommendation.candidate_frequency * 100:.2f}%")
        print(f"Reason: {recommendation.reason}")


def command_target_profit_sensitivity(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = TargetProfitSensitivityEngine(database, config).build_report(
        current_price=current_price,
        profile=args.profile,
    )

    print("=== Target Profit Sensitivity ===")
    print("Dry run only. Production target_profit and trading behavior are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {source}")
    print(f"Current price timestamp: {timestamp}")
    print(f"Configured target_profit: {report.configured_target_profit * 100:.5f}%")
    print(
        f"Effective fee rates: maker={report.fee_rates.maker:.6f} "
        f"taker={report.fee_rates.taker:.6f}"
    )
    print(f"Fee source: {report.fee_rates.source}")
    print("")

    if not report.results or report.results[0].open_cycles_count == 0:
        print("No open paper cycles available for this profile.")
        return

    for item in report.results:
        print(f"--- target_profit {item.target_profit * 100:.5f}% ---")
        print(f"Open cycles count: {item.open_cycles_count}")
        print(f"Would close now count: {item.would_close_now_count}")
        print(f"Would close now rate: {item.would_close_now_rate * 100:.2f}%")
        if item.avg_distance_to_target is None:
            print("Avg distance to target: N/A")
            print("Estimated gross profit range: N/A")
            print("Estimated net profit range: N/A")
        else:
            print(f"Avg distance to target: {item.avg_distance_to_target:.8f}")
            print(
                "Estimated gross profit range: "
                f"{item.gross_profit_min:.8f} .. {item.gross_profit_max:.8f}"
            )
            print(
                "Estimated net profit range: "
                f"{item.net_profit_min:.8f} .. {item.net_profit_max:.8f}"
            )
        print(f"Currently profitable cycles: {item.profitable_now_count}")

    print("--- Recommendation ---")
    if report.recommendation is None:
        print("No tested target_profit would close a currently open profitable cycle now.")
    else:
        print(f"Recommended target_profit: {report.recommendation.target_profit * 100:.5f}%")
        print(f"Reason: {report.recommendation.reason}")


def command_direction_outcome_diagnostics(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = DirectionOutcomeDiagnosticsEngine(database, config).build_report(
        current_price=current_price,
        profile=args.profile,
    )

    print("=== Direction Outcome Diagnostics ===")
    print("Diagnostics only. Trading logic and open cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {source}")
    print(f"Current price timestamp: {timestamp}")
    print("")

    print("--- Open Cycles ---")
    if not report.open_cycles:
        print("No open cycles for this profile.")
    else:
        for item in report.open_cycles:
            moved = "yes" if item.moved_expected_direction else "no"
            print(
                f"db_id={item.db_id} cycle_id={item.cycle_id} "
                f"direction={item.direction} opened_at={item.opened_at} "
                f"age_seconds={item.age_seconds:.0f}"
            )
            print(
                f"  open_price={item.open_price:.8f} current_price={item.current_price:.8f} "
                f"target_price={item.target_price:.8f}"
            )
            print(f"  price moved in expected direction: {moved}")
            print(
                f"  unrealized_pnl={item.unrealized_pnl:.8f} "
                f"distance_from_open={item.distance_from_open:.8f} "
                f"distance_to_target={item.distance_to_target:.8f}"
            )

    summary = report.open_summary
    print("--- Open Cycle Summary ---")
    print(f"BUY cycles count: {summary.buy_cycles_count}")
    print(f"SELL cycles count: {summary.sell_cycles_count}")
    print(f"Moved expected direction count: {summary.moved_expected_direction_count}")
    print(f"Moved against direction count: {summary.moved_against_direction_count}")
    if summary.avg_unrealized_pnl is None:
        print("Avg unrealized pnl: N/A")
        print("Worst unrealized pnl: N/A")
        print("Best unrealized pnl: N/A")
    else:
        print(f"Avg unrealized pnl: {summary.avg_unrealized_pnl:.8f}")
        print(f"Worst unrealized pnl: {summary.worst_unrealized_pnl:.8f}")
        print(f"Best unrealized pnl: {summary.best_unrealized_pnl:.8f}")

    print("--- Historical Direction Outcomes ---")
    if not report.historical_outcomes:
        print("No historical snapshot outcomes available.")
    for item in report.historical_outcomes:
        print(f"N={item.horizon}")
        print(f"  Entry signals evaluated: {item.entry_signals_count}")
        print(f"  BUY signals: {item.buy_signals_count}")
        print(f"  SELL signals: {item.sell_signals_count}")
        print(f"  Moved toward target count: {item.moved_expected_direction_count}")
        print(f"  Moved toward target rate: {item.moved_expected_direction_rate * 100:.2f}%")


def command_trend_alignment_diagnostics(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = TrendAlignmentDiagnosticsEngine(database, config).build_alignment_report(
        profile=args.profile,
        current_price=current_price,
    )

    print("=== 1h Trend Alignment Diagnostics ===")
    print("Diagnostics only. Runtime strategy, open cycles, and trading logic are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {source}")
    print(f"Current price timestamp: {timestamp}")
    print("")

    print("--- Open Cycles ---")
    if not report.open_cycles:
        print("No open cycles for this profile.")
    for item in report.open_cycles:
        print(
            f"db_id={item.db_id} direction={item.direction} opened_at={item.opened_at} "
            f"open_price={item.open_price:.8f} current_price={item.current_price:.8f} "
            f"target_price={item.target_price:.8f}"
        )
        print(
            f"  unrealized_pnl={item.unrealized_pnl:.8f} "
            f"entry_1h_trend={item.entry_1h_trend} current_1h_trend={item.current_1h_trend}"
        )
        print(
            f"  entry aligned with 1h trend: {'yes' if item.entry_aligned_with_1h else 'no'} | "
            f"entry against 1h trend: {'yes' if item.entry_against_1h else 'no'}"
        )

    stats = report.cycle_stats
    print("--- Historical/Paper Cycle Trend Stats ---")
    print(f"Total cycles: {stats.total_cycles}")
    print(f"Aligned cycles: {stats.aligned_cycles}")
    print(f"Against-trend cycles: {stats.against_trend_cycles}")
    print(f"Win rate aligned: {stats.win_rate_aligned * 100:.2f}%")
    print(f"Win rate against-trend: {stats.win_rate_against_trend * 100:.2f}%")
    print(f"Net profit aligned: {stats.net_profit_aligned:.8f}")
    print(f"Net profit against-trend: {stats.net_profit_against_trend:.8f}")


def command_trend_filter_sim(args) -> None:
    config, _logger, database = build_context()
    report = TrendAlignmentDiagnosticsEngine(database, config).build_filter_simulation(profile=args.profile)

    print("=== 1h Trend Filter Simulation ===")
    print("Dry-run only. Runtime profile, strategy config, and open cycles are unchanged.")
    print(f"Profile: {report.profile}")
    if report.current_bad_buy_cycle_db_id is None:
        print("Current adverse BUY cycle: N/A")
    else:
        print(f"Current adverse BUY cycle db_id: {report.current_bad_buy_cycle_db_id}")
    print("")

    for item in report.results:
        print(f"--- {item.name} ---")
        print(f"Candidates total: {item.candidates_total}")
        print(f"Candidates kept: {item.candidates_kept}")
        print(f"Candidates blocked: {item.candidates_blocked}")
        print(
            "Would block current bad BUY cycle: "
            f"{'yes' if item.would_block_current_bad_buy_cycle else 'no'}"
        )
        print(f"Estimated PnL impact: {item.estimated_pnl_impact:.8f}")
        print(f"Hit target count: {item.hit_target_count}")
        print(f"Hit target rate: {item.hit_target_rate * 100:.2f}%")
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print(f"Recommendation: {item.recommendation}")
        print("")


def command_trend_strength_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = TrendStrengthDiagnosticsEngine(database, config).build_report(profile=args.profile)

    print("=== 1h Trend Strength Diagnostics ===")
    print("Dry-run only. Runtime profile, strategy config, and paper cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print("")

    print("=== Candidates ===")
    if not report.candidates:
        print("No candidates available.")
    for item in report.candidates:
        print(
            f"{item.timestamp} | {item.direction} | entry={item.entry_price:.8f} | "
            f"future/current={_format_optional_float(item.comparison_price)} | "
            f"trend={item.trend_label} | change={_format_optional_float(item.one_hour_change)} | "
            f"change_pct={_format_optional_percent(item.one_hour_change_percent)} | "
            f"slope={_format_optional_float(item.one_hour_slope)} | "
            f"range=[{_format_optional_float(item.rolling_min)}, {_format_optional_float(item.rolling_max)}] | "
            f"range_pos={_format_optional_percent(item.position_inside_range)} | "
            f"near_top={item.near_top_of_range} | near_bottom={item.near_bottom_of_range} | "
            f"outcome={item.outcome}"
        )
    print("")

    print("=== Open Cycles ===")
    if not report.open_cycles:
        print("No open cycles for profile.")
    for item in report.open_cycles:
        print(
            f"db_id={item.db_id} | {item.timestamp} | {item.direction} | entry={item.entry_price:.8f} | "
            f"current={_format_optional_float(item.comparison_price)} | trend={item.trend_label} | "
            f"change_pct={_format_optional_percent(item.one_hour_change_percent)} | "
            f"range_pos={_format_optional_percent(item.position_inside_range)} | "
            f"near_top={item.near_top_of_range} | near_bottom={item.near_bottom_of_range} | "
            f"outcome={item.outcome}"
        )
    print("")

    print("=== Flat Relabel Threshold Simulation ===")
    for item in report.simulations:
        print(f"--- {item.name} ---")
        print(f"Candidates total: {item.candidates_total}")
        print(f"Candidates kept: {item.candidates_kept}")
        print(f"Candidates blocked: {item.candidates_blocked}")
        print(f"Bad open cycle blocked: {'yes' if item.bad_open_cycle_blocked else 'no'}")
        print(f"Hit target count: {item.hit_target_count}")
        print(f"Hit target rate: {item.hit_target_rate * 100:.2f}%")
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print("")


def command_range_shift_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = RangeShiftDiagnosticsEngine(database, config).build_report(profile=args.profile)

    print("=== Range Shift Diagnostics ===")
    print("Dry-run only. Runtime profile, strategy config, and paper cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print("")

    print("=== Open Cycles ===")
    if not report.open_cycles:
        print("No open cycles for profile.")
    for item in report.open_cycles:
        print(
            f"db_id={item.db_id} | cycle_id={item.cycle_id} | {item.direction} | "
            f"opened_at={item.opened_at}"
        )
        print(
            f"  open={item.open_price:.8f} | current={item.current_price:.8f} | "
            f"target={item.target_price:.8f}"
        )
        print(
            "  work_center: "
            f"entry={_format_optional_float(item.work_center_at_entry)} | "
            f"current={_format_optional_float(item.current_work_center)}"
        )
        print(
            "  short_center: "
            f"entry={_format_optional_float(item.short_center_at_entry)} | "
            f"current={_format_optional_float(item.current_short_center)}"
        )
        print(
            "  long_center: "
            f"entry={_format_optional_float(item.long_center_at_entry)} | "
            f"current={_format_optional_float(item.current_long_center)}"
        )
        print(
            f"  center_shift={_format_optional_float(item.center_shift_amount)} | "
            f"center_shift_pct={_format_optional_percent(item.center_shift_percent)} | "
            f"direction={item.center_shift_direction}"
        )
        print(
            "  current_observed_1h_range="
            f"[{_format_optional_float(item.current_work_range_min)}, "
            f"{_format_optional_float(item.current_work_range_max)}]"
        )
        print(
            "  target_outside_current_work_range="
            f"{'yes' if item.target_outside_current_work_range else 'no'} | "
            "open_price_no_longer_realistic_mean_reversion_target="
            f"{'yes' if item.open_price_no_longer_realistic_mean_reversion_target else 'no'}"
        )
    print("")

    print("=== Closed Cycles Center Shift ===")
    closed = report.closed_summary
    print(f"Closed cycles evaluated: {closed.closed_cycles_count}")
    print(f"Average center shift to close: {_format_optional_float(closed.average_center_shift_to_close)}")
    print(f"Successful average center shift: {_format_optional_float(closed.successful_average_center_shift)}")
    if not closed.center_shift_distribution:
        print("Center shift distribution: N/A")
    else:
        print("Center shift distribution:")
        for bucket, count in closed.center_shift_distribution:
            print(f"  {bucket}: {count}")
    print("")

    print("=== Dry-run Stale/Rebase Thresholds ===")
    for item in report.threshold_simulations:
        ids = ", ".join(str(value) for value in item.stale_cycle_ids) if item.stale_cycle_ids else "N/A"
        print(
            f"threshold={item.threshold_percent:.3f}% | "
            f"stale_open_cycles={item.stale_open_cycles} | "
            f"rebase_target_candidates={item.rebase_target_candidates} | "
            f"stale_db_ids={ids}"
        )
    print("")
    print("Recommendation note: diagnostics only; no targets are rebased and no cycles are closed.")


def command_target_rebase_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = TargetRebaseDiagnosticsEngine(database, config).build_report(profile=args.profile)

    print("=== Target Rebase Diagnostics ===")
    print("Dry-run only. Runtime targets, strategy config, and paper cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print("")

    print("=== Open Cycles ===")
    if not report.open_cycles:
        print("No open cycles for profile.")
    for item in report.open_cycles:
        print(
            f"db_id={item.db_id} | cycle_id={item.cycle_id} | {item.direction} | "
            f"open={item.open_price:.8f} | original_target={item.original_target:.8f} | "
            f"current={item.current_price:.8f}"
        )
        print(
            f"  observed_1h_low={_format_optional_float(item.observed_1h_low)} | "
            f"observed_1h_high={_format_optional_float(item.observed_1h_high)} | "
            f"current_work_center={_format_optional_float(item.current_work_center)}"
        )
        print(
            f"  target_outside_1h_range={'yes' if item.target_outside_1h_range else 'no'} | "
            f"suggested_rebased_target={_format_optional_float(item.suggested_rebased_target)} | "
            "estimated_rebased_profit_or_loss="
            f"{_format_optional_float(item.estimated_rebased_profit_or_loss)} | "
            f"would_close_if_rebased_now={'yes' if item.would_close_if_rebased_now else 'no'}"
        )
    print("")

    print("=== Dry-run Rebase Scenarios ===")
    for item in report.scenarios:
        print(f"--- {item.name} ---")
        print(f"Affected cycles: {item.affected_cycles}")
        print(f"Would close now: {item.would_close_now}")
        print(f"Estimated PnL: {item.estimated_pnl:.8f}")
        print(f"Remaining open exposure: {item.remaining_open_exposure}")
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print("")


def command_break_even_rebase_sim(args) -> None:
    config, _logger, database = build_context()
    report = BreakEvenRebaseSimulationEngine(database, config).build_report(profile=args.profile)

    print("=== Break-even Rebase Simulation ===")
    print("Dry-run only. Runtime targets, strategy config, and paper cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Open cycles count: {report.open_cycles_count}")
    print(f"Current price: {_format_optional_float(report.current_price)}")
    print(
        "Observed 1h range: "
        f"[{_format_optional_float(report.observed_1h_low)}, "
        f"{_format_optional_float(report.observed_1h_high)}]"
    )
    print("")

    for item in report.scenarios:
        print(f"--- {item.name} ---")
        print(f"Affected open cycles: {item.affected_open_cycles}")
        print(f"Would close now: {item.would_close_now}")
        print(f"Estimated realized PnL: {item.estimated_realized_pnl:.8f}")
        print(f"Remaining open exposure: {item.remaining_open_exposure}")
        print(f"Average distance to rebased target: {_format_optional_float(item.average_distance_to_rebased_target)}")
        print(f"Avoided loss vs nearest range edge: {item.avoided_loss_vs_nearest_range_edge:.8f}")
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print("")


def command_holding_horizon_diagnostics(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = HoldingHorizonDiagnosticsEngine(database, config).build_report(
        current_price=current_price,
        profile=args.profile,
    )

    print("=== Holding Horizon Diagnostics ===")
    print("Diagnostics only. Trading logic and open cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {source}")
    print(f"Current price timestamp: {timestamp}")
    print(f"Configured target_profit: {report.target_profit * 100:.5f}%")
    print("")

    print("--- Historical Holding Horizons ---")
    if not report.horizons:
        print("No historical snapshot data available.")
    for item in report.horizons:
        print(f"N={item.horizon}")
        print(f"  Candidates count: {item.candidates_count}")
        print(f"  Hit target count: {item.hit_target_count}")
        print(f"  Hit rate: {item.hit_rate * 100:.2f}%")
        if item.average_time_to_target is None:
            print("  Average time to target: N/A")
        else:
            print(f"  Average time to target: {item.average_time_to_target:.2f} snapshots")
        if item.max_adverse_movement is None:
            print("  Max adverse movement before target: N/A")
            print("  Average adverse movement: N/A")
        else:
            print(f"  Max adverse movement before target: {item.max_adverse_movement:.8f}")
            print(f"  Average adverse movement: {item.average_adverse_movement:.8f}")
        print(f"  Expired without target count: {item.expired_without_target_count}")

    print("--- Open Cycles Holding State ---")
    if not report.open_cycles:
        print("No open cycles for this profile.")
    for item in report.open_cycles:
        favorable = (
            "N/A"
            if item.max_observed_favorable_movement is None
            else f"{item.max_observed_favorable_movement:.8f}"
        )
        adverse = (
            "N/A"
            if item.max_observed_adverse_movement is None
            else f"{item.max_observed_adverse_movement:.8f}"
        )
        print(
            f"db_id={item.db_id} cycle_id={item.cycle_id} direction={item.direction} "
            f"age_seconds={item.age_seconds:.0f}"
        )
        print(
            f"  open_price={item.open_price:.8f} target_price={item.target_price:.8f} "
            f"current_price={item.current_price:.8f}"
        )
        print(f"  distance_to_target={item.distance_to_target:.8f}")
        print(f"  max observed favorable movement: {favorable}")
        print(f"  max observed adverse movement: {adverse}")


def command_profile_comparison_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = ProfileComparisonDiagnosticsEngine(database, config).build_report()

    print("=== Profile Comparison Diagnostics ===")
    print("Diagnostics only. Production strategy logic, config, and open cycles are unchanged.")
    print(
        f"Effective fee rates: maker={report.fee_rates.maker:.6f} "
        f"taker={report.fee_rates.taker:.6f}"
    )
    print(f"Fee source: {report.fee_rates.source}")
    print(f"Configured target_profit: {report.target_profit * 100:.5f}%")
    print("")

    if not report.results:
        print("No profile comparison data available.")
        return

    for item in report.results:
        print(f"--- {item.profile} ---")
        print(
            f"Rules: BUY <= {item.buy_threshold:.0f}, SELL >= {item.sell_threshold:.0f}, "
            f"micro_trend={item.micro_trend_mode}"
        )
        print(f"Candidate count: {item.candidate_count}")
        print(f"BUY count: {item.buy_count}")
        print(f"SELL count: {item.sell_count}")
        print(f"Candidate frequency: {item.candidate_frequency * 100:.2f}%")
        print("Target hit rate:")
        for hit_rate in item.target_hit_rates:
            print(
                f"  N={hit_rate.horizon}: "
                f"{hit_rate.hit_target_count}/{item.candidate_count} "
                f"({hit_rate.hit_rate * 100:.2f}%)"
            )

        if item.average_favorable_movement is None:
            print("Average favorable movement: N/A")
            print("Average adverse movement: N/A")
            print("Best movement: N/A")
            print("Worst movement: N/A")
        else:
            print(f"Average favorable movement: {item.average_favorable_movement:.8f}")
            print(f"Average adverse movement: {item.average_adverse_movement:.8f}")
            print(f"Best movement: {item.best_movement:.8f}")
            print(f"Worst movement: {item.worst_movement:.8f}")

        if item.gross_profit_min is None:
            print("Estimated gross profit range: N/A")
            print("Estimated net profit range: N/A")
        else:
            print(
                f"Estimated gross profit range: "
                f"{item.gross_profit_min:.8f} .. {item.gross_profit_max:.8f}"
            )
            print(
                f"Estimated net profit range: "
                f"{item.net_profit_min:.8f} .. {item.net_profit_max:.8f}"
            )
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print("")


def command_post_entry_path_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = PostEntryPathDiagnosticsEngine(database, config).build_report(profile=args.profile)

    print("=== Post Entry Path Diagnostics ===")
    print("Diagnostics only. Trading logic, config, and open cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Configured target_profit: {report.target_profit * 100:.5f}%")
    print("")

    if not report.candidates:
        print("No post-entry path data available.")
        return

    print("--- Candidates ---")
    for index, item in enumerate(report.candidates, start=1):
        print(f"Candidate #{index}")
        print(f"  Timestamp: {item.timestamp}")
        print(f"  Direction: {item.direction}")
        print(f"  Entry price: {item.entry_price:.8f}")
        print(f"  Target price: {item.target_price:.8f}")
        print(f"  Work position: {item.work_position:.4f}")
        print(f"  Micro trend: {item.micro_trend}")
        print("  Next prices:")
        for horizon, price in item.next_prices:
            price_text = "N/A" if price is None else f"{price:.8f}"
            print(f"    N={horizon}: {price_text}")

        favorable = (
            "N/A"
            if item.max_favorable_movement is None
            else f"{item.max_favorable_movement:.8f}"
        )
        adverse = (
            "N/A"
            if item.max_adverse_movement is None
            else f"{item.max_adverse_movement:.8f}"
        )
        print(f"  Max favorable movement: {favorable}")
        print(f"  Max adverse movement: {adverse}")
        print(f"  Did hit target: {item.did_hit_target}")
        print(f"  Did move halfway to target: {item.did_move_halfway_to_target}")
        print(f"  Did reverse against entry: {item.did_reverse_against_entry}")
        print(f"  Failure mode: {item.failure_mode}")

    summary = report.summary
    print("--- Aggregate Summary ---")
    print(f"Candidates count: {summary.candidates_count}")
    print(f"Hit target rate: {summary.hit_target_rate * 100:.2f}%")
    print(f"Halfway-to-target rate: {summary.halfway_to_target_rate * 100:.2f}%")
    if summary.average_max_favorable_movement is None:
        print("Average max favorable movement: N/A")
        print("Average max adverse movement: N/A")
        print("Average time to best favorable movement: N/A")
    else:
        print(f"Average max favorable movement: {summary.average_max_favorable_movement:.8f}")
        print(f"Average max adverse movement: {summary.average_max_adverse_movement:.8f}")
        print(
            "Average time to best favorable movement: "
            f"{summary.average_time_to_best_favorable_movement:.2f} snapshots"
        )
    print(f"Common failure mode: {summary.common_failure_mode}")
    if summary.failure_modes:
        print("Failure modes:")
        for mode, count in summary.failure_modes:
            print(f"  {mode}: {count}")


def command_entry_confirmation_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = EntryConfirmationDiagnosticsEngine(database, config).build_report(profile=args.profile)

    print("=== Entry Confirmation Diagnostics ===")
    print("Dry run only. Production trading logic and profile behavior are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Configured target_profit: {report.target_profit * 100:.5f}%")
    print(f"Evaluation horizon: {report.horizon} snapshots")
    print("")

    if not report.results:
        print("No entry confirmation data available.")
        return

    for item in report.results:
        print(f"--- {item.variant} ---")
        print(f"Base candidate count: {item.base_candidate_count}")
        print(f"Candidate count: {item.candidate_count}")
        print(f"Hit target count: {item.hit_target_count}")
        print(f"Hit target rate: {item.hit_target_rate * 100:.2f}%")
        print(f"Halfway count: {item.halfway_count}")
        print(f"Halfway rate: {item.halfway_rate * 100:.2f}%")
        print(f"Immediate adverse move count: {item.immediate_adverse_move_count}")
        print(f"Immediate adverse move rate: {item.immediate_adverse_move_rate * 100:.2f}%")
        if item.average_favorable_movement is None:
            print("Avg favorable movement: N/A")
            print("Avg adverse movement: N/A")
        else:
            print(f"Avg favorable movement: {item.average_favorable_movement:.8f}")
            print(f"Avg adverse movement: {item.average_adverse_movement:.8f}")
        print(f"Missed opportunities count: {item.missed_opportunities_count}")
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print("")


def command_partial_target_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = PartialTargetDiagnosticsEngine(database, config).build_report(profile=args.profile)

    print("=== Partial Target Diagnostics ===")
    print("Dry run only. Production trading logic and target_profit are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Base target_profit: {report.base_target_profit * 100:.5f}%")
    print(f"Evaluation horizon: {report.horizon} snapshots")
    print(
        f"Effective fee rates: maker={report.fee_rates.maker:.6f} "
        f"taker={report.fee_rates.taker:.6f}"
    )
    print(f"Fee source: {report.fee_rates.source}")
    print("")

    if not report.results:
        print("No partial target data available.")
        return

    for item in report.results:
        print(f"--- Target multiplier {item.multiplier * 100:.0f}% ---")
        print(f"Candidate count: {item.candidate_count}")
        print(f"Hit count: {item.hit_count}")
        print(f"Hit rate: {item.hit_rate * 100:.2f}%")
        if item.estimated_gross_profit_min is None:
            print("Estimated gross profit: N/A")
            print("Estimated net profit: N/A")
        else:
            print(
                f"Estimated gross profit: "
                f"{item.estimated_gross_profit_min:.8f} .. {item.estimated_gross_profit_max:.8f}"
            )
            print(
                f"Estimated net profit: "
                f"{item.estimated_net_profit_min:.8f} .. {item.estimated_net_profit_max:.8f}"
            )
        if item.average_time_to_target is None:
            print("Average time to target: N/A")
            print("Max adverse movement before hit: N/A")
        else:
            print(f"Average time to target: {item.average_time_to_target:.2f} snapshots")
            print(f"Max adverse movement before hit: {item.max_adverse_movement_before_hit:.8f}")
        print(f"Missed / failed count: {item.missed_failed_count}")
        print(f"Recommendation score: {item.recommendation_score:.2f}")
        print("")

    print("--- Interpretation ---")
    print(f"50% target significantly improves hit-rate: {report.fifty_percent_target_better}")
    print(f"75% target still acceptable: {report.seventy_five_percent_target_acceptable}")


def command_exit_risk_diagnostics(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = ExitRiskDiagnosticsEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Exit Risk Diagnostics ===")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print("")
    print("--- Open cycles risk ---")
    if not report.open_cycles:
        print("No open cycles for this profile.")
    for item in report.open_cycles:
        print(
            f"db_id={item.db_id} | direction={item.direction} | profile={item.profile} | "
            f"age={_format_duration(item.age_seconds)}"
        )
        print(
            f"  open_price={item.open_price:.8f} | current_price={item.current_price:.8f} | "
            f"target_price={item.target_price:.8f}"
        )
        print(
            f"  unrealized_pnl={item.unrealized_pnl:.8f} | "
            f"distance_to_target={item.distance_to_target:.8f} | "
            f"adverse_move={item.adverse_move_percent:.5f}%"
        )
        print("  would_stop_at:")
        for threshold, would_stop in item.would_stop_at.items():
            print(f"  - {threshold:.3f}%: {'yes' if would_stop else 'no'}")
    print("")
    print("--- Historical closed/open cycles summary ---")
    summary = report.historical_summary
    print(f"Closed net profit: {summary.closed_net_profit:.8f}")
    print(f"Open unrealized pnl: {summary.open_unrealized_pnl:.8f}")
    print(f"Combined realized + unrealized pnl: {summary.combined_realized_unrealized_pnl:.8f}")
    print(f"Best closed profit: {_format_optional_float(summary.best_closed_profit)}")
    print(f"Worst open unrealized loss: {_format_optional_float(summary.worst_open_unrealized_loss)}")
    print(f"Avg holding time closed cycles: {_format_optional_duration(summary.avg_holding_time_closed_seconds)}")
    print(f"Avg age open cycles: {_format_optional_duration(summary.avg_age_open_seconds)}")
    print("")
    print("--- Max holding simulation ---")
    for item in report.max_holding_results:
        print(f"{_format_duration(item.max_age_seconds)}: would_timeout={item.would_timeout_count}")
    print("")
    print("--- Recommendation ---")
    print(report.recommendation)


def command_max_holding_sensitivity(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = MaxHoldingSensitivityEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Max Holding Sensitivity ===")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Total cycles: {report.total_cycles}")
    print("")
    if not report.results:
        print("No max holding sensitivity data available.")
        return

    for item in report.results:
        print(f"--- Max holding: {_format_duration(item.max_age_seconds)} ---")
        print(f"Cycles affected: {item.cycles_affected}")
        print(f"Would close by timeout: {item.would_close_by_timeout}")
        print(f"Timeout close estimated PnL: {item.timeout_close_estimated_pnl:.8f}")
        print(f"Realized target closes: {item.realized_target_closes}")
        print(f"Combined PnL: {item.combined_pnl:.8f}")
        print(f"Win rate including timeout closes: {item.win_rate_including_timeouts * 100:.2f}%")
        print(f"Worst timeout loss: {_format_optional_float(item.worst_timeout_loss)}")
        print(f"Recommendation score: {item.recommendation_score:.8f}")
        print("")

    print("--- Recommendation ---")
    if report.recommended_max_age_seconds is None:
        print("No recommendation: no cycles available.")
    else:
        print(f"Best tested max holding: {_format_duration(report.recommended_max_age_seconds)}")


def command_exit_rule_sim(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = ExitRuleSimulationEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Exit Rule Simulation ===")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Total cycles: {report.total_cycles}")
    print("")
    if not report.results:
        print("No exit rule simulation data available.")
        return

    for item in report.results:
        print(f"--- {item.rule_name} ---")
        print(f"Closed target profit: {item.closed_target_profit:.8f}")
        print(f"Simulated stop/timeout losses: {item.simulated_stop_timeout_losses:.8f}")
        print(f"Combined PnL: {item.combined_pnl:.8f}")
        print(f"Win rate: {item.win_rate * 100:.2f}%")
        print(f"Max loss: {_format_optional_float(item.max_loss)}")
        print(f"Avg holding time: {_format_optional_duration(item.avg_holding_time_seconds)}")
        print(
            "Open exposure after rules: "
            f"{item.open_exposure_count} cycles | notional={item.open_exposure_notional:.8f}"
        )
        print(f"Recommendation score: {item.recommendation_score:.8f}")
        print("")

    print("--- Recommendation ---")
    print(f"Best tested exit rule: {report.recommended_rule or 'N/A'}")


def command_exit_rule_optimizer(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = ExitRuleOptimizerEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Exit Rule Optimizer ===")
    print("Dry-run only. Runtime close rules and paper cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Total cycles: {report.total_cycles}")
    print("")
    if not report.scenarios:
        print("No exit rule optimizer data available.")
        return

    for item in report.scenarios:
        print(f"--- {item.scenario} ---")
        print(f"Simulated total net including forced exits: {item.simulated_total_net:.8f}")
        print(f"Automatic target closes: {item.automatic_target_closes}")
        print(f"Forced exits count: {item.forced_exits_count}")
        print(f"Forced exits net: {item.forced_exits_net:.8f}")
        print(f"Manual stale cycles avoided: {item.manual_stale_cycles_avoided}")
        print(f"Average holding time: {_format_optional_duration(item.average_holding_time_seconds)}")
        print(f"Worst loss: {_format_optional_float(item.worst_loss)}")
        print(f"Recommendation score: {item.recommendation_score:.8f}")
        print("")

    print("--- Recommendation ---")
    print(f"Best tested exit rule: {report.recommended_scenario or 'N/A'}")


def command_exit_tolerance_sim(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = ExitToleranceSimulationEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Exit Tolerance Simulation ===")
    print("Dry-run only. Runtime close rules and paper cycles are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Open cycles count: {report.open_cycles_count}")
    print(f"Existing closed cycles count: {report.existing_closed_cycles_count}")
    print("")

    if not report.results:
        print("No exit tolerance simulation data available.")
        return

    print("--- Tolerance Results ---")
    for item in report.results:
        print(f"Tolerance: {item.tolerance_name}")
        print(f"  Tolerance value: {item.tolerance_value:.8f}")
        print(f"  Affected cycles: {item.affected_cycles}")
        print(f"  Would close now: {item.would_close_now}")
        print(f"  Estimated PnL: {item.estimated_pnl:.8f}")
        print(f"  Difference vs strict target: {item.difference_vs_strict_target:.8f}")
        print(f"  Closed cycles count: {item.closed_cycles_count}")
        print(f"  Open cycles remaining: {item.open_cycles_remaining}")
        print(f"  Recommendation score: {item.recommendation_score:.8f}")
        print("")

    print("--- Open Cycles ---")
    if not report.open_cycle_details:
        print("No open cycles for profile.")
    for item in report.open_cycle_details:
        matching = ", ".join(item.matching_tolerances) if item.matching_tolerances else "none"
        print(
            f"db_id={item.db_id} | direction={item.direction} | "
            f"current_price={item.current_price:.8f} | target_price={item.target_price:.8f}"
        )
        print(
            f"  distance_to_target={item.distance_to_target:.8f} | "
            f"would_close_under={matching}"
        )

    print("")
    print("--- Recommendation ---")
    print(f"Best tested tolerance: {report.recommended_tolerance or 'N/A'}")


def command_high_frequency_diagnostics(args) -> None:
    config, _logger, database = build_context()
    report = HighFrequencyDiagnosticsEngine(database, config).build_report()

    print("=== High Frequency Diagnostics ===")
    print("Diagnostics only. Runtime strategy profiles and trading logic are unchanged.")
    print(f"Total market samples: {report.total_samples}")
    print(f"Sample span hours: {report.sample_span_hours:.4f}")
    print(f"Estimated sample interval seconds: {report.estimated_sample_interval_seconds:.2f}")
    print("")

    print("--- Current Mean Reversion Frequency ---")
    print(f"Current candidate count: {report.current_candidate_count}")
    print(f"Current candidate rate: {report.current_candidate_rate * 100:.2f}%")
    print(f"Paper closed cycles for mean_reversion_v2_small_target: {report.current_closed_cycles}")
    print(f"Approx current cycles/day: {report.current_cycles_per_day:.2f}")
    print("")

    print("--- Current Entry Blockers ---")
    if not report.current_blockers:
        print("No blocker data available.")
    for item in report.current_blockers:
        print(f"- {item.name}: {item.count} ({item.rate * 100:.2f}%)")
    print("")

    print("--- Micro Entry Scenarios ---")
    for item in report.micro_entry_scenarios:
        print(f"{item.name}: {item.candidate_count} candidates ({item.candidate_rate * 100:.2f}%)")
        print(f"  {item.description}")
        print(f"  BUY: {item.buy_count} | SELL: {item.sell_count}")
        if item.top_blockers:
            blockers = ", ".join(f"{blocker.name}={blocker.count}" for blocker in item.top_blockers[:5])
            print(f"  top blockers: {blockers}")
    print("")

    print("--- Target Sweep ---")
    for item in report.target_results:
        avg_holding = (
            f"{item.average_holding_seconds:.2f} sec"
            if item.average_holding_seconds is not None
            else "N/A"
        )
        print(
            f"target={item.target_percent:.4f}% | candidates={item.candidate_count} | "
            f"hits={item.hit_count} | hit_rate={item.hit_rate * 100:.2f}% | "
            f"avg_holding={avg_holding} | cycles/hour={item.theoretical_cycles_per_hour:.2f} | "
            f"cycles/day={item.theoretical_cycles_per_day:.2f}"
        )
    print("")

    print("--- Frequency Choking Filters ---")
    for item in report.choking_filters[:8]:
        print(f"- {item.name}: {item.count} ({item.rate * 100:.2f}%)")
    print("")

    print("--- Fit Comparison ---")
    print(f"Potential cycles/hour: {report.potential_cycles_per_hour:.2f}")
    print(f"Potential cycles/day: {report.potential_cycles_per_day:.2f}")
    print(f"Better fit for original idea: {report.better_fit}")
    print(f"Recommendation: {report.recommendation}")


def command_collect_market_snapshots(args) -> None:
    config, logger, database = build_context()
    collector = HighFrequencySnapshotCollector(database, config)

    print("=== High Frequency Market Snapshot Collector ===")
    print("Diagnostics-only collector. No paper cycles, no orders, no runtime strategy changes.")
    print(f"Symbol: {config.symbol}")
    print(f"Duration hours: {args.duration_hours}")
    print(f"Interval seconds: {args.interval}")
    if args.max_snapshots:
        print(f"Max snapshots: {args.max_snapshots}")

    logger.info(
        "HF market snapshot collector started: duration_hours=%s interval=%s max_snapshots=%s",
        args.duration_hours,
        args.interval,
        args.max_snapshots,
    )
    result = collector.collect(
        duration_hours=args.duration_hours,
        interval_seconds=args.interval,
        max_snapshots=args.max_snapshots,
    )

    print("--- Result ---")
    print(f"Snapshots collected: {result.snapshots_collected}")
    print(f"Duration seconds: {result.duration_seconds:.2f}")
    print(f"Interval seconds: {result.interval_seconds:.2f}")


def command_high_frequency_dataset_summary(args) -> None:
    _config, _logger, database = build_context()
    summary = HighFrequencyDatasetSummaryEngine(database).build_summary()

    print("=== High Frequency Dataset Summary ===")
    print(f"Snapshots: {summary.total_snapshots}")
    print(f"Potential micro-entry: {summary.potential_micro_entries}")
    print(f"Potential micro-entry rate: {summary.potential_micro_entry_rate * 100:.2f}%")
    _print_hf_distribution("By hour", summary.by_hour)
    _print_hf_distribution("By session", summary.by_session)
    _print_hf_distribution("Blockers", summary.blockers)
    _print_hf_distribution("Spread distribution", summary.spread_distribution)
    _print_hf_distribution("Micro trend distribution", summary.micro_trend_distribution)
    _print_hf_distribution("Work position distribution", summary.work_position_distribution)


def _print_hf_distribution(title: str, rows: list[tuple[str, int]]) -> None:
    print("")
    print(f"--- {title} ---")
    if not rows:
        print("No data.")
    for name, count in rows:
        print(f"- {name}: {count}")


def command_micro_cycle_sim(args) -> None:
    config, _logger, database = build_context()
    report = MicroCycleSimulationEngine(database, config).build_report(
        scenario=args.scenario,
        target_percent=args.target,
        max_holding_seconds=args.max_holding_seconds,
    )

    print("=== High Frequency Micro Cycle Simulation ===")
    print("Diagnostics only. No paper cycles, no orders, no runtime strategy changes.")
    print(f"Symbol: {config.symbol}")
    if args.scenario:
        print(f"Scenario filter: {args.scenario}")
    if args.target is not None:
        print(f"Target filter: {args.target:.5f}%")
    if args.max_holding_seconds is not None:
        print(f"Max holding seconds: {args.max_holding_seconds:.2f}")
    print("")

    if not report.results:
        print("No high-frequency snapshots available.")
        print(f"Recommendation: {report.recommendation}")
        return

    for result in report.results:
        avg_holding = _format_optional_seconds(result.average_holding_seconds)
        median_holding = _format_optional_seconds(result.median_holding_seconds)
        max_holding = _format_optional_seconds(result.max_holding_seconds_observed)
        print(
            f"{result.scenario} | target={result.target_percent:.5f}% | "
            f"opened={result.cycles_opened} target_closed={result.closed_by_target} "
            f"timeout_closed={result.closed_by_timeout} open_end={result.still_open_at_end} | "
            f"win_rate={result.win_rate * 100:.2f}% | net={result.net_profit:.8f} | "
            f"avg_net={result.average_net_per_cycle:.8f} | avg_hold={avg_holding} | "
            f"median_hold={median_holding} | max_hold={max_holding} | "
            f"worst_unrealized={result.worst_unrealized_loss:.8f} | "
            f"skipped_active={result.skipped_opportunities_due_to_active_cycle} | "
            f"used_rate={result.opportunities_used_rate * 100:.2f}% | "
            f"cycles/hour={result.cycles_per_hour:.2f} | cycles/day={result.estimated_cycles_per_day:.2f} | "
            f"score={result.recommendation_score:.4f}"
        )
        print(
            f"  target: net={result.target_net_profit:.8f} win_rate={result.target_win_rate * 100:.2f}% "
            f"avg={result.target_avg_net:.8f} best={result.target_best_profit:.8f} "
            f"worst={result.target_worst_loss:.8f}"
        )
        print(
            f"  timeout: net={result.timeout_net_profit:.8f} win_rate={result.timeout_win_rate * 100:.2f}% "
            f"avg={result.timeout_avg_net:.8f} best={result.timeout_best_profit:.8f} "
            f"worst={result.timeout_worst_loss:.8f} profits={result.timeout_profit_count} "
            f"losses={result.timeout_loss_count}"
        )
        print(
            f"  risk: max_loss_streak={result.max_consecutive_losses} "
            f"max_timeout_loss_streak={result.max_consecutive_timeout_losses} "
            f"realized_drawdown={result.max_drawdown_by_realized_equity:.8f} "
            f"worst_cycle={result.worst_realized_cycle:.8f} best_cycle={result.best_realized_cycle:.8f}"
        )
        print(
            f"  distribution: positive={result.positive_cycles_count} negative={result.negative_cycles_count} "
            f"breakeven={result.breakeven_cycles_count} "
            f"top1_share={result.profit_share_from_top_1_cycle * 100:.2f}% "
            f"top3_share={result.profit_share_from_top_3_cycles * 100:.2f}% "
            f"top5_share={result.profit_share_from_top_5_cycles * 100:.2f}%"
        )
        if args.show_cycles:
            _print_micro_cycle_details(result.cycles)

    print("")
    print("--- Summary Recommendation ---")
    best = report.best_result
    if best is None:
        print("Best scenario: N/A")
        print("Best target: N/A")
        print("Best result: N/A")
    else:
        print(f"Best scenario: {best.scenario}")
        print(f"Best target: {best.target_percent:.5f}%")
        print(
            "Best result: "
            f"cycles/day={best.estimated_cycles_per_day:.2f}, "
            f"net_profit={best.net_profit:.8f}, "
            f"average_holding={_format_optional_seconds(best.average_holding_seconds)}"
        )
    print(f"Recommendation: {report.recommendation}")


def _format_optional_seconds(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}s"


def _print_micro_cycle_details(cycles) -> None:
    if not cycles:
        print("  cycles: no closed simulated cycles.")
        return

    important = sorted(cycles, key=lambda cycle: cycle.net_profit)[:3]
    important.extend(sorted(cycles, key=lambda cycle: cycle.net_profit, reverse=True)[:3])
    important.extend(cycles[-5:])
    seen = set()
    selected = []
    for cycle in important:
        key = (cycle.opened_at, cycle.closed_at, cycle.direction, cycle.entry_price, cycle.exit_price)
        if key in seen:
            continue
        seen.add(key)
        selected.append(cycle)

    print("  cycles:")
    for cycle in selected:
        print(
            "    "
            f"opened_at={cycle.opened_at} closed_at={cycle.closed_at} direction={cycle.direction} "
            f"entry={cycle.entry_price:.8f} exit={cycle.exit_price:.8f} "
            f"reason={cycle.close_reason} hold={cycle.holding_seconds:.2f}s "
            f"net={cycle.net_profit:.8f} max_unrealized_loss={cycle.max_unrealized_loss:.8f}"
        )


def command_micro_cycle_grid_search(args) -> None:
    config, _logger, database = build_context()
    engine = MicroCycleGridSearchEngine(database, config)
    report = engine.run(
        scenario=args.scenario,
        min_cycles_day=args.min_cycles_day,
        max_drawdown=args.max_drawdown,
        top=args.top,
    )

    if args.export_csv:
        output_path = engine.export_csv(args.export_csv, report.results)
        print(f"CSV exported: {output_path}")

    print("=== Micro Cycle Grid Search ===")
    print("Diagnostics only. No paper cycles, no orders, no runtime strategy changes.")
    print(f"Total combinations: {report.total_results}")
    if args.scenario:
        print(f"Scenario filter: {args.scenario}")
    print(f"Top size: {args.top}")
    print("")

    _print_micro_cycle_grid_section("Top by recommendation score", report.top_by_score, engine)
    _print_micro_cycle_grid_section("Top by net profit", report.top_by_net_profit, engine)
    _print_micro_cycle_grid_section("Top by cycles/day with positive net", report.top_by_cycles_per_day, engine)
    _print_micro_cycle_grid_section("Best balanced candidates", report.balanced_candidates, engine)


def command_hf_micro_grid_sim(args) -> None:
    config, _logger, database = build_context()
    report = HFMicroGridSimulationEngine(database, config).build_report(
        scenario=args.scenario,
        target_percent=args.target,
        max_holding_seconds=args.max_holding_seconds,
        layer_size=args.layer_size,
        max_layers=args.max_layers,
        directional_exposure_guard=args.directional_exposure_guard,
        guard_min_layers=args.guard_min_layers,
        guard_loss_threshold=args.guard_loss_threshold,
    )

    print("=== HF Micro Grid Simulation ===")
    print("Diagnostics only. No paper cycles, no orders, no runtime strategy changes.")
    print("Baseline: mean_reversion_hf_micro_v1")
    print(f"Scenario: {report.scenario}")
    print(f"Target: {report.target_percent:.5f}%")
    print(f"Max holding/layer spacing: {report.max_holding_seconds:.2f}s")
    print(f"Layer size: {report.layer_size:.2f} USD")
    print(f"Maximum layers: {report.max_layers}")
    print(f"Directional exposure guard: {'ON' if report.directional_exposure_guard else 'OFF'}")
    if report.directional_exposure_guard:
        print(f"Guard min layers: {report.guard_min_layers}")
        print(f"Guard loss threshold: {report.guard_loss_threshold:.8f}")
    print("")
    print("Total:")
    print(f"- opened layers: {report.opened_layers}")
    print(f"- closed layers: {report.closed_layers}")
    print(f"- active layers: {report.active_layers}")
    print(f"- cycles/hour: {report.cycles_per_hour:.2f}")
    print(f"- estimated cycles/day: {report.estimated_cycles_per_day:.2f}")
    print("")
    print("Capital:")
    print(f"- average capital used: {report.average_capital_used:.2f}")
    print(f"- maximum capital used: {report.maximum_capital_used:.2f}")
    print(f"- average layers in market: {report.average_layers_in_market:.2f}")
    print(f"- maximum simultaneous layers: {report.maximum_simultaneous_layers}")
    print("")
    print("Profit:")
    print(f"- gross profit: {report.gross_profit:.8f}")
    print(f"- net profit: {report.net_profit:.8f}")
    print(f"- average profit per layer: {report.average_profit_per_layer:.8f}")
    print(f"- median profit: {report.median_profit:.8f}")
    print("")
    print("Close-Only Risk:")
    print(f"- close-only realized drawdown: {report.max_drawdown:.8f}")
    print(f"- worst unrealized drawdown: {report.worst_unrealized_drawdown:.8f}")
    print(f"- longest recovery: {_format_optional_seconds(report.longest_recovery_seconds)}")
    print(
        "- all layers occupied: "
        f"{report.all_layers_occupied_count} times, "
        f"avg={_format_optional_seconds(report.all_layers_average_duration_seconds)}, "
        f"longest={_format_optional_seconds(report.all_layers_longest_duration_seconds)}"
    )
    print("")
    print("Realistic Risk:")
    print(f"- max realized drawdown: {report.max_realized_drawdown:.8f}")
    print(f"- max unrealized drawdown: {report.max_unrealized_drawdown:.8f}")
    print(f"- max total equity drawdown: {report.max_total_equity_drawdown:.8f}")
    print(f"- worst open basket loss: {report.worst_open_basket_loss:.8f}")
    print(f"- worst single layer unrealized loss: {report.worst_single_layer_unrealized_loss:.8f}")
    print(f"- longest time underwater: {_format_optional_seconds(report.longest_time_underwater_seconds)}")
    print(
        "- recovery after worst drawdown: "
        f"{_format_optional_seconds(report.recovery_time_after_worst_drawdown_seconds)}"
    )
    print(
        "- longest time with max layers used: "
        f"{_format_optional_seconds(report.longest_time_with_max_layers_used_seconds)}"
    )
    print(
        "- capital exposure time: "
        f"50%={_format_optional_seconds(report.time_with_50_percent_capital_used_seconds)}, "
        f"80%={_format_optional_seconds(report.time_with_80_percent_capital_used_seconds)}, "
        f"100%={_format_optional_seconds(report.time_with_100_percent_capital_used_seconds)}"
    )
    print(f"- final active layers: {report.final_active_layers}")
    print(f"- final unrealized pnl: {report.final_unrealized_pnl:.8f}")
    print(f"- final total equity pnl: {report.final_total_equity_pnl:.8f}")
    print(f"- final capital locked: {report.final_capital_locked:.2f}")
    if report.worst_basket_snapshot is None:
        print("- worst basket snapshot: N/A")
    else:
        snapshot = report.worst_basket_snapshot
        print(
            "- worst basket snapshot: "
            f"timestamp={snapshot.timestamp} active_layers={snapshot.active_layers_count} "
            f"capital_locked={snapshot.capital_locked:.2f} realized={snapshot.realized_pnl:.8f} "
            f"unrealized={snapshot.unrealized_pnl:.8f} total={snapshot.total_equity_pnl:.8f} "
            f"worst_layer={snapshot.worst_layer_direction}@{snapshot.worst_layer_entry_price:.8f} "
            f"worst_layer_unrealized={snapshot.worst_layer_unrealized_pnl:.8f}"
        )
    print("")
    print("Occupancy histogram:")
    for layer_count in sorted(report.occupancy_histogram):
        print(f"- {layer_count} layers: {report.occupancy_histogram[layer_count]}")
    print("")
    print("Timeout:")
    print(f"- timeout closes: {report.timeout_closes}")
    print(f"- timeout wins: {report.timeout_wins}")
    print(f"- timeout losses: {report.timeout_losses}")
    print("")
    print("Target:")
    print(f"- target closes: {report.target_closes}")
    print(f"- target wins: {report.target_wins}")
    print("")
    print("Skipped opportunities:")
    print(f"- all layers occupied: {report.skipped_opportunities_no_layer}")
    print(f"- layer spacing active: {report.skipped_opportunities_spacing}")
    print("")
    print("Directional Exposure Guard:")
    print(f"- enabled: {'yes' if report.directional_exposure_guard else 'no'}")
    print(f"- guard_min_layers: {report.guard_min_layers}")
    print(f"- guard_loss_threshold: {report.guard_loss_threshold:.8f}")
    print(f"- directional_guard_blocks: {report.directional_guard_blocks}")
    print(f"- blocked BUY layers: {report.directional_guard_buy_blocks}")
    print(f"- blocked SELL layers: {report.directional_guard_sell_blocks}")
    print("")
    print("Comparison vs mean_reversion_hf_micro_v1:")
    comparison = report.comparison
    print(
        f"- HF v1: net={comparison.baseline_net_profit:.8f}, "
        f"drawdown={comparison.baseline_drawdown:.8f}, cycles/day={comparison.baseline_cycles_per_day:.2f}"
    )
    print(
        f"- HF Grid: net={comparison.grid_net_profit:.8f}, "
        f"drawdown={comparison.grid_drawdown:.8f}, cycles/day={comparison.grid_cycles_per_day:.2f}, "
        f"capital_utilization={comparison.capital_utilization * 100:.2f}%"
    )
    print(f"- verdict: {comparison.verdict}")
    if report.grid_v1_comparison is not None:
        grid_v1 = report.grid_v1_comparison
        print("")
        print("Comparison vs HF Grid v1:")
        print(
            f"- Grid v1: net={grid_v1.grid_v1_net_profit:.8f}, "
            f"drawdown={grid_v1.grid_v1_drawdown:.8f}, cycles/day={grid_v1.grid_v1_cycles_per_day:.2f}"
        )
        print(
            f"- Guarded Grid: net={grid_v1.guarded_net_profit:.8f}, "
            f"drawdown={grid_v1.guarded_drawdown:.8f}, cycles/day={grid_v1.guarded_cycles_per_day:.2f}"
        )
        print(f"- verdict: {grid_v1.verdict}")
    print("")
    print(f"Recommendation score: {report.recommendation_score:.4f}")
    print(f"Recommendation: {report.recommendation}")
    if args.show_drawdown_events:
        _print_hf_grid_drawdown_diagnostics(report, args.drawdown_events_limit)


def _print_hf_grid_drawdown_diagnostics(report, limit: int) -> None:
    diagnostics = report.drawdown_diagnostics
    print("")
    print("=== HF Grid Drawdown Diagnostics ===")
    print(f"Top drawdown events shown: {min(limit, len(diagnostics.events))} / {len(diagnostics.events)}")
    if not diagnostics.events:
        print("No drawdown events available.")
        print("")
    for index, event in enumerate(diagnostics.events[:limit], start=1):
        layer_ages = ", ".join(f"{age:.0f}s" for age in event.layer_ages_seconds)
        print(f"--- Drawdown Event #{index} ---")
        print(f"timestamp: {event.timestamp}")
        print(f"total_equity_drawdown: {event.total_equity_drawdown:.8f}")
        print(f"total_equity_pnl: {event.total_equity_pnl:.8f}")
        print(f"realized_pnl: {event.realized_pnl:.8f}")
        print(f"unrealized_pnl: {event.unrealized_pnl:.8f}")
        print(f"active_layers_count: {event.active_layers_count}")
        print(f"capital_locked: {event.capital_locked:.2f}")
        print(f"dominant_direction: {event.dominant_direction}")
        print(f"buy_layers_count: {event.buy_layers_count}")
        print(f"sell_layers_count: {event.sell_layers_count}")
        print(f"buy_unrealized_pnl: {event.buy_unrealized_pnl:.8f}")
        print(f"sell_unrealized_pnl: {event.sell_unrealized_pnl:.8f}")
        print(f"price: {event.price:.8f}")
        print(f"short_center: {event.short_center:.8f}")
        print(f"distance_from_short_center: {event.distance_from_short_center:.8f}")
        print(f"price_buffer_unique_values: {event.price_buffer_unique_values}")
        print(f"flat_samples_count: {event.flat_samples_count}")
        print(f"layer_ages: {layer_ages}")
        print(f"oldest_layer_age: {_format_optional_seconds(event.oldest_layer_age_seconds)}")
        print(f"newest_layer_age: {_format_optional_seconds(event.newest_layer_age_seconds)}")
        print(f"worst_layer_id: {event.worst_layer_id}")
        print(f"worst_layer_direction: {event.worst_layer_direction}")
        print(f"worst_layer_entry_price: {event.worst_layer_entry_price:.8f}")
        print(f"worst_layer_unrealized_pnl: {event.worst_layer_unrealized_pnl:.8f}")
        print("")

    print("Drawdown by active layer count:")
    _print_hf_grid_drawdown_bucket(diagnostics.by_active_layer_count)
    print("Drawdown by dominant direction:")
    _print_hf_grid_drawdown_bucket(diagnostics.by_dominant_direction)
    print("Drawdown by session:")
    _print_hf_grid_drawdown_bucket(diagnostics.by_session)
    print("Drawdown by flat/non-flat state:")
    _print_hf_grid_drawdown_bucket(diagnostics.by_flat_state)
    print("Aggregated drawdown causes:")
    print(
        "- average drawdown before recovery: "
        f"{_format_optional_seconds(diagnostics.average_drawdown_before_recovery)}"
    )
    print(
        "- adding next layer made drawdown worse: "
        f"{diagnostics.layer_additions_worsened_drawdown_count} / {diagnostics.layer_additions_count}"
    )
    print(
        "- next layer eventually recovered basket: "
        f"{diagnostics.layer_additions_recovered_count} / {diagnostics.layer_additions_count}"
    )
    print("Recommendations:")
    for recommendation in diagnostics.recommendations:
        print(f"- {recommendation}")


def _print_hf_grid_drawdown_bucket(rows) -> None:
    if not rows:
        print("- N/A")
        return
    for key, bucket in sorted(rows.items(), key=lambda item: str(item[0])):
        print(
            f"- {key}: count={bucket.count} "
            f"avg_drawdown={bucket.average_drawdown:.8f} worst_drawdown={bucket.worst_drawdown:.8f}"
        )


def command_hf_micro_grid_guard_sweep(args) -> None:
    config, _logger, database = build_context()
    engine = HFMicroGridGuardSweepEngine(database, config)
    report = engine.run(
        top=args.top,
        min_cycles_day=args.min_cycles_day,
        max_drawdown=args.max_drawdown,
        max_average_capital=args.max_average_capital,
    )

    print("=== HF Micro Grid Directional Guard Sweep ===")
    print("Diagnostics only. No paper cycles, no orders, no runtime strategy changes.")
    print("Base parameters: scenario=short_term_mean_reversion target=0.00050% layer_size=10 max_layers=10 spacing=180s")
    print(f"Total guard variants: {report.total_results}")
    print("")
    reference = report.grid_v1_reference
    print("Reference rows:")
    print(
        f"- Grid v1 no guard: net={reference.net_profit:.8f}, "
        f"cycles/day={reference.estimated_cycles_per_day:.2f}, "
        f"drawdown={reference.max_total_equity_drawdown:.8f}, "
        f"worst_basket={reference.worst_open_basket_loss:.8f}, "
        f"max_layers={reference.maximum_simultaneous_layers}, "
        f"avg_capital={reference.average_capital_used:.2f}, "
        f"recommendation={reference.recommendation}"
    )
    print(
        f"- HF v1 baseline: net={reference.comparison.baseline_net_profit:.8f}, "
        f"cycles/day={reference.comparison.baseline_cycles_per_day:.2f}, "
        f"drawdown={reference.comparison.baseline_drawdown:.8f}"
    )
    print("")
    _print_hf_grid_guard_sweep_section("Top by recommendation score", report.top_by_score)
    _print_hf_grid_guard_sweep_section(
        "Top by net profit with drawdown better than -0.015",
        report.top_by_net_profit_with_drawdown,
    )
    _print_hf_grid_guard_sweep_section(
        "Top by lowest drawdown with positive net",
        report.top_by_lowest_drawdown_positive_net,
    )
    _print_hf_grid_guard_sweep_section("Balanced candidates", report.balanced_candidates)
    _print_hf_grid_guard_sweep_recommendation(report)

    if args.export_csv:
        output_path = engine.export_csv(args.export_csv, report.results)
        print(f"CSV exported: {output_path}")


def _print_hf_grid_guard_sweep_recommendation(report) -> None:
    print("Final recommendation:")
    if not report.balanced_candidates:
        print("- No balanced candidates found under current risk threshold.")
        print("- HF Grid remains research-only.")
        print("- Do not promote HF Grid to a paper profile yet.")
        print("- Baseline remains mean_reversion_hf_micro_v1.")
        print("- Next research direction: improve HF v1 entry direction using hf-losing-cycle-diagnostics.")
        print("")
        return
    print("- Balanced candidates exist, but HF Grid should remain diagnostics-only until manually reviewed.")
    print("- Compare every candidate against mean_reversion_hf_micro_v1 before any paper-profile decision.")
    print("")


def _print_hf_grid_guard_sweep_section(title: str, rows) -> None:
    print(f"--- {title} ---")
    if not rows:
        print("No matching candidates.")
        print("")
        return
    for item in rows:
        print(
            f"min_layers={item.guard_min_layers} | loss_threshold={item.guard_loss_threshold:.8f} | "
            f"net={item.net_profit:.8f} | cycles/day={item.estimated_cycles_per_day:.2f} | "
            f"drawdown={item.max_total_equity_drawdown:.8f} | "
            f"worst_basket={item.worst_open_basket_loss:.8f} | "
            f"max_layers={item.maximum_simultaneous_layers} | avg_capital={item.average_capital_used:.2f} | "
            f"blocks={item.directional_guard_blocks} | buy={item.directional_guard_buy_blocks} | "
            f"sell={item.directional_guard_sell_blocks} | score={item.recommendation_score:.4f} | "
            f"recommendation={item.recommendation}"
        )
    print("")


def _print_micro_cycle_grid_section(title: str, rows, engine: MicroCycleGridSearchEngine) -> None:
    print(f"--- {title} ---")
    if not rows:
        print("No matching candidates.")
        print("")
        return
    for item in rows:
        print(
            f"{item.scenario} | target={item.target_percent:.5f}% | "
            f"max_hold={item.max_holding_seconds:.0f}s | opened={item.cycles_opened} | "
            f"target={item.closed_by_target} timeout={item.closed_by_timeout} open_end={item.still_open_at_end} | "
            f"win={item.win_rate * 100:.2f}% | net={item.net_profit:.8f} | "
            f"avg_net={item.average_net_per_cycle:.8f} | avg_hold={_format_optional_seconds(item.average_holding_seconds)} | "
            f"median_hold={_format_optional_seconds(item.median_holding_seconds)} | "
            f"cycles/day={item.estimated_cycles_per_day:.2f} | drawdown={item.max_drawdown_by_realized_equity:.8f} | "
            f"timeout_net={item.timeout_net_profit:.8f} | timeout_avg={item.timeout_avg_net:.8f} | "
            f"timeout_losses={item.timeout_loss_count} | loss_streak={item.max_consecutive_losses} | "
            f"timeout_loss_streak={item.max_consecutive_timeout_losses} | "
            f"top5_share={item.profit_share_from_top_5_cycles * 100:.2f}% | "
            f"recommendation={engine.recommendation_for(item)} | score={item.recommendation_score:.4f}"
        )
    print("")


def command_target_resolution_diagnostics(args) -> None:
    config, _logger, database = build_context()
    engine = TargetResolutionDiagnosticsEngine(database, config)

    print("=== Target Resolution Diagnostics ===")
    print("Diagnostics only. Runtime, paper trading, and strategy profiles are unchanged.")
    print(f"Symbol: {config.symbol}")
    print(f"Price tick size: {config.price_tick_size:.8f}")
    print("")

    if args.compare:
        report = engine.compare(args.compare[0], args.compare[1])
        _print_target_resolution_item("First target", report.first)
        _print_target_resolution_item("Second target", report.second)
        print("--- Compare ---")
        print(f"Identical after floor normalization: {report.identical_after_floor_normalization}")
        print(f"Identical after ceil normalization: {report.identical_after_ceil_normalization}")
        print(f"Identical after rounding: {report.identical_after_rounding}")
        print(f"Identical after epsilon: {report.identical_after_epsilon}")
        print(f"Identical after BUY target calculation: {report.identical_after_buy_target_calculation}")
        print(f"Identical after SELL target calculation: {report.identical_after_sell_target_calculation}")
        if report.warning:
            print(f"WARNING: {report.warning}")
        return

    if args.compare_simulation:
        report = engine.compare_simulation(
            args.compare_simulation[0],
            args.compare_simulation[1],
            scenario=args.scenario,
            max_holding_seconds=args.max_holding_seconds,
        )
        print("--- Simulation Compare ---")
        print(f"Scenario: {report.scenario}")
        print(f"Max holding seconds: {_format_optional_seconds(report.max_holding_seconds)}")
        print(f"Total samples: {report.total_samples}")
        print(f"First target: {report.first_target_percent:.5f}% cycles={report.first_cycles}")
        print(f"Second target: {report.second_target_percent:.5f}% cycles={report.second_cycles}")
        print(f"Compared cycles: {report.compared_cycles}")
        print(f"Different outcome: {report.different_outcomes}")
        print(f"Identical outcome: {report.identical_outcomes}")
        print(f"Similarity: {report.similarity * 100:.2f}%")
        print(report.message)
        return

    report = engine.build_report()
    print(f"Reference price: {report.reference_price:.8f}")
    print("--- Target Resolution ---")
    for item in report.items:
        _print_target_resolution_item("Target", item)
    print("--- Equivalent Effective Targets ---")
    if not report.equivalent_groups:
        print("No equivalent effective targets detected by ceil tick normalization.")
    else:
        for group in report.equivalent_groups:
            values = ", ".join(f"{target:.5f}%" for target in group)
            print(f"WARNING: Equivalent effective target group: {values}")


def _print_target_resolution_item(title: str, item) -> None:
    print(f"--- {title} ---")
    print(f"Requested target: {item.requested_target_percent:.5f}%")
    print(f"Reference price: {item.reference_price:.8f}")
    print(f"Raw target distance: {item.raw_target_distance:.10f}")
    print(f"Target distance in ticks: {item.raw_ticks:.4f}")
    print(f"Minimum possible price move: {item.minimum_price_move:.8f}")
    print(f"Floor ticks: {item.floor_ticks}")
    print(f"Ceil ticks: {item.ceil_ticks}")
    print(f"Rounded ticks: {item.rounded_ticks}")
    print(f"Effective target by floor ticks: {item.floor_effective_target_percent:.5f}%")
    print(f"Effective target by ceil ticks: {item.ceil_effective_target_percent:.5f}%")
    print(f"Effective target by rounded ticks: {item.rounded_effective_target_percent:.5f}%")
    print(f"BUY target raw: {item.buy_target_raw:.8f}")
    print(f"BUY target floor tick: {item.buy_target_floor_tick:.8f}")
    print(f"BUY target ceil tick: {item.buy_target_ceil_tick:.8f}")
    print(f"SELL target raw: {item.sell_target_raw:.8f}")
    print(f"SELL target floor tick: {item.sell_target_floor_tick:.8f}")
    print(f"SELL target ceil tick: {item.sell_target_ceil_tick:.8f}")
    print(f"Close epsilon reference: {item.close_epsilon:.8f}")
    print(f"Epsilon in ticks: {item.epsilon_ticks:.4f}")
    if item.has_sub_tick_distance:
        print("WARNING: Requested target distance is smaller than one configured price tick.")
    print("")


def command_market_session_diagnostics(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = MarketSessionDiagnosticsEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Market Session Diagnostics ===")
    print("Diagnostics only. Trading logic and paper cycles are unchanged.")
    print("Session hours use the timestamp hour stored in SQLite.")
    print("ASIA=00-07, LONDON=08-12, LONDON_NEW_YORK_OVERLAP=13-16, NEW_YORK=17-23.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print("")

    print("--- Session Summary ---")
    for item in report.session_stats:
        print(f"Session: {item.session}")
        print(f"  Total entries: {item.total_entries}")
        print(f"  Closed cycles: {item.closed_cycles}")
        print(f"  Open cycles: {item.open_cycles}")
        print(f"  Win rate: {item.win_rate * 100:.2f}%")
        print(f"  Net profit: {item.net_profit:.8f}")
        print(f"  Average holding time: {_format_optional_duration(item.average_holding_time_seconds)}")
        print(f"  Average unrealized PnL: {_format_optional_float(item.average_unrealized_pnl)}")
        print(f"  Target hit rate: {item.target_hit_rate * 100:.2f}%")
        print("")

    print("--- Entry Hour Distribution ---")
    _print_hour_distribution(report.entry_hour_distribution)
    print("")
    print("--- Close Hour Distribution ---")
    _print_hour_distribution(report.close_hour_distribution)


def command_session_filter_sim(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = SessionFilterSimulationEngine(database, config).build_report(
        profile=args.profile,
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
    )

    print("=== Session Filter Simulation ===")
    print("Dry-run only. Runtime filters, strategy config, and paper cycles are unchanged.")
    print("ASIA=00-07, LONDON=08-12, LONDON_NEW_YORK_OVERLAP=13-16, NEW_YORK=17-23.")
    print(f"Profile: {report.profile}")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Total cycles: {report.total_cycles}")
    print("")

    if not report.results:
        print("No session filter simulation data available.")
        return

    for item in report.results:
        print(f"--- {item.scenario} ---")
        print(f"Entries: {item.entries}")
        print(f"Closed cycles: {item.closed_cycles}")
        print(f"Win rate: {item.win_rate * 100:.2f}%")
        print(f"Net profit: {item.net_profit:.8f}")
        print(f"Avg holding time: {_format_optional_duration(item.average_holding_time_seconds)}")
        print(f"Avg unrealized PnL: {_format_optional_float(item.average_unrealized_pnl)}")
        print(f"Target hit rate: {item.target_hit_rate * 100:.2f}%")
        print(f"Current open cycle blocked: {'yes' if item.current_open_cycle_blocked else 'no'}")
        print(f"Historical bad cycles blocked: {'yes' if item.historical_bad_cycles_blocked else 'no'}")
        print(f"Recommendation score: {item.recommendation_score:.8f}")
        print("")

    print("--- Recommendation ---")
    print(f"Best tested session filter: {report.recommended_scenario or 'N/A'}")


def _print_hour_distribution(distribution: dict[int, int]) -> None:
    shown = False
    for hour in range(24):
        count = distribution.get(hour, 0)
        if count <= 0:
            continue
        shown = True
        print(f"{hour:02d}:00 | {count}")
    if not shown:
        print("No data.")


def command_build_ml_dataset(args) -> None:
    config, _logger, _database = build_context()
    provider = BinanceMarketDataProvider(base_url=config.binance_base_url)
    historical = HistoricalDataProvider(provider)
    candles = historical.get_candles(
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
    )
    result = MLDatasetExporter(config).export(
        candles=candles,
        symbol=args.symbol,
        interval=args.interval,
        profile=args.profile,
        dataset_mode=args.dataset_mode,
    )

    print("=== ML Dataset Export ===")
    print(f"Symbol: {args.symbol}")
    print(f"Interval: {args.interval}")
    print(f"Limit requested: {args.limit}")
    print(f"Candles loaded: {len(candles)}")
    print(f"Profile: {args.profile}")
    print(f"Dataset mode: {args.dataset_mode}")
    print(f"Rows written: {result.rows_written}")
    print(f"Candidate rows: {result.candidate_rows}")
    print(f"Output: {result.path}")


def command_ml_dataset_coverage(args) -> None:
    config, _logger, _database = build_context()
    provider = BinanceMarketDataProvider(base_url=config.binance_base_url)
    historical = HistoricalDataProvider(provider)
    candles = historical.get_candles(
        symbol=args.symbol,
        interval=args.interval,
        limit=args.limit,
    )
    report = MLDatasetCoverageEngine(config).build_report(
        candles=candles,
        profile=args.profile,
        dataset_mode=args.dataset_mode,
    )

    print("=== ML Dataset Coverage ===")
    print(f"Symbol: {args.symbol}")
    print(f"Interval: {args.interval}")
    print(f"Limit requested: {args.limit}")
    print(f"Candles loaded: {len(candles)}")
    print(f"Profile: {report.profile}")
    print(f"Dataset mode: {report.dataset_mode}")
    print(f"Total rows: {report.total_rows}")
    print(f"Candidate rows: {report.candidate_rows}")
    print(f"BUY zone count: {report.buy_zone_count}")
    print(f"SELL zone count: {report.sell_zone_count}")
    print(f"Work position min: {_format_optional_float(report.work_position_min)}")
    print(f"Work position max: {_format_optional_float(report.work_position_max)}")
    print(f"Work position avg: {_format_optional_float(report.work_position_avg)}")
    print("Micro trend distribution:")
    if report.micro_trend_distribution:
        for name, count in report.micro_trend_distribution.items():
            print(f"- {name}: {count}")
    else:
        print("- No micro trend data")
    print("Filter pass counts:")
    print(f"- entry zone: {report.entry_zone_pass_count}")
    print(f"- micro_trend: {report.micro_trend_pass_count}")
    print(f"- safety filters: {report.safety_filters_pass_count}")
    print(f"- all filters: {report.all_filters_pass_count}")
    print(f"Recommendation: {report.recommendation}")


def command_ml_dataset_summary(args) -> None:
    report = MLDatasetSummaryEngine().build_report(args.file)

    print("=== ML Dataset Summary ===")
    print(f"File: {report.file_path}")
    print(f"Total rows: {report.total_rows}")
    print(f"Candidate rows: {report.candidate_rows}")
    print(f"Target hit positive count: {report.target_hit_positive_count}")
    print(f"Target hit negative count: {report.target_hit_negative_count}")
    print(f"Positive rate: {report.positive_rate * 100:.2f}%")
    print("BUY/SELL distribution:")
    if report.direction_distribution:
        for direction, count in report.direction_distribution.items():
            print(f"- {direction}: {count}")
    else:
        print("- No candidate directions")
    _print_ml_dataset_group_summary("Target hit rate by direction", report.target_hit_rate_by_direction)
    _print_ml_dataset_group_summary(
        "Target hit rate by work_position bucket",
        report.target_hit_rate_by_work_position_bucket,
    )
    _print_ml_dataset_group_summary(
        "Target hit rate by volatility regime",
        report.target_hit_rate_by_volatility_regime,
    )
    _print_ml_dataset_group_summary("Target hit rate by hour of day", report.target_hit_rate_by_hour)


def command_train_ml_baseline(args) -> None:
    report = MLBaselineTrainer().train(args.file)

    print("=== ML Baseline Training Report ===")
    print(f"Dataset file: {report.file_path}")
    print(f"Train rows: {report.train_rows}")
    print(f"Test rows: {report.test_rows}")
    print(f"Positive rate train: {report.train_positive_rate * 100:.2f}%")
    print(f"Positive rate test: {report.test_positive_rate * 100:.2f}%")
    print(f"Precision: {_format_ml_metric(report.precision)}")
    print(f"Recall: {_format_ml_metric(report.recall)}")
    print(f"F1: {_format_ml_metric(report.f1)}")
    print(f"ROC-AUC: {_format_ml_metric(report.roc_auc)}")
    print(f"PR-AUC: {_format_ml_metric(report.pr_auc)}")
    print("Confusion matrix [actual 0/1 rows, predicted 0/1 columns]:")
    for row in report.confusion_matrix:
        print(f"- {row}")
    print("Top feature importances:")
    if report.top_feature_importances:
        for item in report.top_feature_importances:
            print(f"- {item.name}: {item.importance:.6f}")
    else:
        print("- N/A")
    if report.warning:
        print(f"Warning: {report.warning}")
    print(f"Output: {report.output_path}")


def _format_ml_metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _print_ml_dataset_group_summary(title: str, rows) -> None:
    print(f"{title}:")
    if not rows:
        print("- No candidate data")
        return
    for row in rows:
        print(
            f"- {row.name}: total={row.total} positive={row.positives} "
            f"rate={row.positive_rate * 100:.2f}%"
        )


def _format_duration(seconds: float | int) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining_seconds}s"
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _format_optional_duration(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    return _format_duration(seconds)


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.8f}"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.4f}%"


def command_validation_summary(args) -> None:
    _config, _logger, database = build_context()
    summary = ValidationSummaryEngine(database).build_summary(profile=args.profile)

    print("=== Validation Summary ===")
    print(f"Profile: {summary.profile}")
    print(f"Overall status: {summary.overall_status}")
    print(f"Strategy signals: {summary.strategy_signals}")
    print(f"Latest backtest trades: {summary.latest_backtest_trades}")
    print(f"Latest backtest net profit: {summary.latest_backtest_net_profit:.8f}")
    print(f"Paper cycles: {summary.paper_cycles}")
    print(f"Paper closed cycles: {summary.paper_closed_cycles}")
    print(f"Paper net profit: {summary.paper_net_profit:.8f}")
    print(f"Paper insights rating: {summary.paper_insights_rating}")
    if summary.risk_blocked_rate_available:
        print(f"Risk blocked rate: {summary.risk_blocked_rate * 100:.2f}%")
    else:
        print("Risk blocked rate: N/A (profile-specific risk blocked rate unavailable)")
    print("Warnings:")
    if summary.warnings:
        for item in summary.warnings:
            print(f"- {item}")
    else:
        print("- None")
    print("Next action:")
    print(summary.next_action)


def command_profile_performance_summary(args) -> None:
    _config, _logger, database = build_context()
    summary = ProfilePerformanceSummaryEngine(database).build_summary(profile=args.profile)

    PaperTradingCliRenderer().render_profile_performance_summary(summary)
    print("Best cycle:")
    _print_profile_cycle_summary(summary.best_cycle)
    print("Worst cycle:")
    _print_profile_cycle_summary(summary.worst_cycle)
    print("Session breakdown:")
    for item in summary.session_breakdown:
        _print_profile_breakdown(item)


def command_paper_profit_concentration(args) -> None:
    _config, _logger, database = build_context()
    summary = PaperProfitConcentrationEngine(database).build_summary(
        profile=args.profile,
        since_id=args.since_id,
    )

    print("=== Paper Profit Concentration ===")
    print(f"Profile: {summary.profile}")
    print(f"Since id: {summary.since_id}")
    print(f"Realized cycles: {summary.realized_cycles_count}")
    if summary.realized_cycles_count == 0:
        print("No realized paper cycles available.")
        print(f"Recommendation: {summary.recommendation}")
        return

    print(f"Total net profit: {summary.total_net_profit:.8f}")
    print(f"Best cycle net: {summary.best_cycle_net:.8f}")
    print(f"Worst cycle net: {summary.worst_cycle_net:.8f}")
    print(f"Net without best 1: {summary.net_without_best_1:.8f}")
    print(f"Net without best 3: {summary.net_without_best_3:.8f}")
    print(f"Net without best 5: {summary.net_without_best_5:.8f}")
    print(f"Top 1 profit share: {summary.top1_profit_share * 100:.2f}%")
    print(f"Top 3 profit share: {summary.top3_profit_share * 100:.2f}%")
    print(f"Top 5 profit share: {summary.top5_profit_share * 100:.2f}%")
    print(f"Positive cycles count: {summary.positive_cycles_count}")
    print(f"Negative cycles count: {summary.negative_cycles_count}")
    print(f"Breakeven cycles count: {summary.breakeven_cycles_count}")
    print(f"Positive net total: {summary.positive_net_total:.8f}")
    print(f"Negative net total: {summary.negative_net_total:.8f}")
    print(f"Average positive cycle: {summary.average_positive_cycle:.8f}")
    print(f"Average negative cycle: {summary.average_negative_cycle:.8f}")
    print(f"Median net: {summary.median_net:.8f}")
    print(f"Target closed net: {summary.target_closed_net:.8f}")
    print(f"Timeout closed net: {summary.timeout_closed_net:.8f}")
    print(f"Target closed count: {summary.target_closed_count}")
    print(f"Timeout closed count: {summary.timeout_closed_count}")
    print(f"Timeout loss count: {summary.timeout_loss_count}")
    print(f"Timeout avg net: {summary.timeout_avg_net:.8f}")
    print(f"Recommendation: {summary.recommendation}")


def command_paper_outlier_validation(args) -> None:
    _config, _logger, database = build_context()
    summary = PaperOutlierValidationEngine(database).build_summary(
        profile=args.profile,
        since_id=args.since_id,
    )

    print("=== Paper Outlier Validation ===")
    print(f"Profile: {summary.profile}")
    print(f"Since id: {summary.since_id}")
    print(f"Total cycles: {summary.total_cycles}")
    if summary.total_cycles == 0:
        print("No realized paper cycles available.")
        print(f"Recommendation: {summary.recommendation}")
        return

    print(f"Total net: {summary.total_net:.8f}")
    print(f"Best cycle net: {summary.best_cycle_net:.8f}")
    print(f"Worst cycle net: {summary.worst_cycle_net:.8f}")
    print(f"Median net: {summary.median_net:.8f}")
    print(f"Trimmed net without top 1: {summary.trimmed_net_without_top_1:.8f}")
    print(f"Trimmed net without top 3: {summary.trimmed_net_without_top_3:.8f}")
    print(f"Trimmed net without top 5: {summary.trimmed_net_without_top_5:.8f}")
    print(f"Winsorized net top 1 to median: {summary.winsorized_net_top_1_to_median:.8f}")
    print(f"Winsorized net top 3 to median: {summary.winsorized_net_top_3_to_median:.8f}")
    print(f"Positive cycles count: {summary.positive_cycles_count}")
    print(f"Negative cycles count: {summary.negative_cycles_count}")
    print(f"Breakeven cycles count: {summary.breakeven_cycles_count}")
    print(f"Target closed count: {summary.target_closed_count}")
    print(f"Timeout closed count: {summary.timeout_closed_count}")
    print(f"Target net: {summary.target_net:.8f}")
    print(f"Timeout net: {summary.timeout_net:.8f}")
    print(
        "Net without outliers positive: "
        f"{'yes' if summary.net_without_outliers_positive_or_not else 'no'}"
    )
    print(f"Top 1 profit share: {summary.top1_profit_share * 100:.2f}%")
    print(f"Top 5 profit share: {summary.top5_profit_share * 100:.2f}%")
    print(f"Outlier risk: {summary.outlier_risk}")
    if summary.total_cycles < 100:
        print("Sample size warning: total cycles < 100.")
    print(f"Recommendation: {summary.recommendation}")


def command_hf_losing_cycle_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    report = HFLosingCycleDiagnosticsEngine(database).build_report(
        profile=args.profile,
        since_id=args.since_id,
        limit=args.limit,
    )

    print("=== HF Losing Cycle Diagnostics ===")
    print(f"Profile: {report.profile}")
    print(f"Since id: {report.since_id}")
    print(f"Limit: {report.limit if report.limit is not None else 'N/A'}")
    print("")
    print("Summary:")
    print(f"Total cycles: {report.total_cycles}")
    print(f"Losing cycles count: {report.losing_cycles_count}")
    print(f"Losing cycles rate: {report.losing_cycles_rate * 100:.2f}%")
    print(f"Total loss net: {report.total_loss_net:.8f}")
    print(f"Average loss: {report.average_loss:.8f}")
    print(f"Median loss: {report.median_loss:.8f}")
    print(f"Worst loss: {report.worst_loss:.8f}")
    print(f"BUY losses: count={report.buy_losses_count} net={report.buy_losses_net:.8f}")
    print(f"SELL losses: count={report.sell_losses_count} net={report.sell_losses_net:.8f}")
    print(f"Timeout losses: count={report.timeout_losses_count} net={report.timeout_losses_net:.8f}")
    print(f"Target losses: count={report.target_losses_count} net={report.target_losses_net:.8f}")
    print("")
    print("Loss categories:")
    if report.categories:
        for item in report.categories:
            print(
                f"- {item.category}: count={item.count} "
                f"net={item.net_loss:.8f} avg={item.average_loss:.8f}"
            )
    else:
        print("- No losing cycles.")
    print("")
    print("Losing cycles:")
    if report.details:
        for detail in report.details:
            print(
                f"- db_id={detail.db_id} direction={detail.direction} "
                f"open={detail.open_price:.8f} close={detail.close_price:.8f} "
                f"target={detail.target_price:.8f} net={detail.net_profit:.8f} "
                f"reason={detail.close_reason} category={detail.category}"
            )
            print(
                f"  holding={_format_optional_duration(detail.holding_time_seconds)} "
                f"immediate_adverse={detail.immediate_adverse_move} "
                f"against_short_center_movement={detail.against_short_center_movement} "
                f"flat_before_entry={detail.flat_before_entry} "
                f"last_different_fallback={detail.last_different_fallback_used}"
            )
            print(
                f"  entry_context: short_center={detail.short_center_at_entry} "
                f"entry_price={detail.current_price_at_entry} previous_price={detail.previous_price} "
                f"last_different_price={detail.last_different_price} "
                f"hf_entry_mode={detail.hf_entry_mode} "
                f"unique_values={detail.price_buffer_unique_values} "
                f"flat_samples={detail.flat_samples_count} flat_buffer={detail.flat_price_buffer}"
            )
            print(
                f"  movement: max_favorable={detail.max_favorable_move} "
                f"max_adverse={detail.max_adverse_move} "
                f"target_touched={detail.did_price_ever_touch_target_before_timeout} "
                f"min_distance_to_target={detail.minimum_distance_to_target} "
                f"near_target_samples={detail.near_target_samples} "
                f"price_at_timeout_close={detail.price_at_timeout_close}"
            )
    else:
        print("- No losing cycles.")
    print("")
    print("Recommendations:")
    for item in report.recommendations:
        print(f"- {item}")


def command_hf_profit_audit(args) -> None:
    _config, _logger, database = build_context()
    report = HFProfitAuditEngine(database).build_report(
        profile=args.profile,
        since_id=args.since_id,
    )

    print("=== HF Profit Audit ===")
    print(f"Profile: {report.profile}")
    print(f"Since ID: {report.since_id if report.since_id is not None else 'N/A'}")
    print(f"Total cycles: {report.total_cycles}")
    print(f"Closed cycles: {report.closed_cycles}")
    print(f"Profile total net: {report.total_net_profit:+.8f}")
    print(f"Latest 100 cycles net: {report.latest_100_net_profit:+.8f}")
    print(f"Latest 250 cycles net: {report.latest_250_net_profit:+.8f}")
    print(f"Latest 500 cycles net: {report.latest_500_net_profit:+.8f}")
    print(f"Current run cycles: {report.current_run_cycles}")
    print(f"Current run net: {report.current_run_net_profit:+.8f}")
    print(f"Extreme close cycles: {report.extreme_close_cycles_count}")
    print(f"Extreme close net: {report.extreme_close_net_profit:+.8f}")
    print(f"Extreme close profit share: {report.extreme_close_profit_share * 100:.2f}%")
    print(f"Net without extreme close cycles: {report.net_without_extreme_close_cycles:+.8f}")
    print("")
    print("Best cycle:")
    print(_format_hf_profit_audit_cycle(report.best_cycle))
    print("Worst cycle:")
    print(_format_hf_profit_audit_cycle(report.worst_cycle))
    _print_hf_profit_audit_cycles("Top 10 cycles by net_profit", report.top_cycles)
    _print_hf_profit_audit_cycles("Suspicious high PnL cycles", report.suspicious_cycles)
    _print_hf_profit_audit_cycles("Abnormal quantity cycles", report.abnormal_quantity_cycles)
    _print_hf_profit_audit_cycles("Abnormal open/close distance cycles", report.abnormal_distance_cycles)
    _print_hf_profit_audit_cycles("Fallback/extreme close price cycles", report.fallback_price_cycles)


def command_hf_extreme_move_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    report = HFExtremeMoveDiagnosticsEngine(database).build_report(args.profile)

    print("=== HF Extreme Move Diagnostics ===")
    print(f"Profile: {report.profile}")
    print(f"Total closed cycles: {report.total_cycles}")
    print(f"Lifetime net: {report.lifetime_net_profit:+.8f}")
    print(f"Known extreme close prices: {_format_price_list(report.known_extreme_close_prices)}")
    print(f"Observed min close price: {_format_optional_price(report.observed_min_close_price)}")
    print(f"Observed max close price: {_format_optional_price(report.observed_max_close_price)}")
    print("")
    print("Extreme contribution:")
    print(f"- extreme cycles: {report.extreme_cycles_count}")
    print(f"- extreme net: {report.extreme_net_profit:+.8f}")
    print(f"- extreme profit share: {report.extreme_profit_share * 100:.2f}%")
    print(f"- net without extreme cycles: {report.net_without_extreme_cycles:+.8f}")
    print(f"- recommendation: {report.recommendation}")
    print("")
    print("Recent vs lifetime windows:")
    for window in report.windows:
        print(
            f"- {window.label}: cycles={window.cycles_count} "
            f"net={window.net_profit:+.8f} extreme_cycles={window.extreme_cycles_count} "
            f"extreme_net={window.extreme_net_profit:+.8f} "
            f"extreme_share={window.extreme_profit_share * 100:.2f}% "
            f"net_without_extreme={window.net_without_extreme_cycles:+.8f}"
        )

    _print_hf_extreme_cycles("Top 10 profit cycles", report.top_profit_cycles)
    _print_hf_extreme_cycles("Extreme close price cycles", report.extreme_close_cycles)
    print("")
    print("Best extreme cycle:")
    print(_format_hf_extreme_cycle(report.best_extreme_cycle))
    print("Worst extreme cycle:")
    print(_format_hf_extreme_cycle(report.worst_extreme_cycle))


def command_hf_run_regime_comparison(args) -> None:
    _config, _logger, database = build_context()
    run_a_since_id = args.run_a_since_id
    if run_a_since_id is None:
        run_a_since_id = args.good_since_id if args.good_since_id is not None else 0
    run_b_since_id = args.run_b_since_id
    if run_b_since_id is None:
        run_b_since_id = args.bad_since_id if args.bad_since_id is not None else 0
    report = HFRunRegimeComparisonEngine(database).compare(
        profile=args.profile,
        run_a_since_id=int(run_a_since_id),
        run_b_since_id=int(run_b_since_id),
        limit=args.limit,
    )

    print("=== HF Run Regime Comparison ===")
    print(f"Profile: {report.profile}")
    _print_hf_run_regime_series(report.run_a)
    _print_hf_run_regime_series(report.run_b)
    print("")
    print("Comparison summary:")
    for item in report.differences:
        print(f"- {item}")
    print(f"Recommendation: {report.recommendation}")


def command_hf_velocity_filter_sim(args) -> None:
    _config, _logger, database = build_context()
    report = HFVelocityFilterSimulationEngine(database).simulate(
        profile=args.profile,
        since_id=args.since_id,
        velocity_threshold=args.velocity_threshold,
        drift_threshold=args.drift_threshold,
        require_direction_confirmed=args.require_direction_confirmed,
        limit=args.limit,
    )

    print("=== HF Velocity Filter Simulation ===")
    print(f"Profile: {report.profile}")
    print(f"Since ID: {report.since_id}")
    print(f"Limit: {report.limit if report.limit is not None else 'N/A'}")
    print(f"Cycles loaded: {report.cycles_count}")
    print(f"Entry context available: {report.entry_context_available}")
    print(f"Entry context missing: {report.entry_context_missing}")
    print(f"Baseline net without extreme: {report.baseline_net_without_extreme:+.8f}")
    print(f"Baseline cycles/day: {report.baseline_cycles_per_day:.2f}")
    print("")
    print("Scenario results:")
    for scenario in report.scenarios:
        print(
            f"- {scenario.scenario}: "
            f"original={scenario.original_cycles} "
            f"kept={scenario.kept_cycles} blocked={scenario.blocked_cycles} "
            f"blocked_winners={scenario.blocked_winners} "
            f"blocked_losers={scenario.blocked_losers} "
            f"net_kept_no_ext={scenario.net_kept_without_extreme:+.8f} "
            f"net_blocked_no_ext={scenario.net_blocked_without_extreme:+.8f} "
            f"improvement={scenario.net_improvement_vs_baseline:+.8f} "
            f"win_kept={scenario.win_rate_kept * 100:.2f}% "
            f"timeout_loss_kept={scenario.timeout_losses_kept} "
            f"timeout_loss_blocked={scenario.timeout_losses_blocked} "
            f"cycles_day={scenario.cycles_per_day_estimate_after_filter:.2f} "
            f"extreme_kept={scenario.kept_extreme_cycles} "
            f"extreme_blocked={scenario.blocked_extreme_cycles} "
            f"recommendation={scenario.recommendation}"
        )


def command_hf_regime_filter_sim(args) -> None:
    _config, _logger, database = build_context()
    report = HFRegimeFilterSimulationEngine(database).simulate(
        profile=args.profile,
        since_id=args.since_id,
        limit=args.limit,
        velocity_threshold=args.velocity_threshold,
    )

    print("=== HF Regime-aware Velocity Filter Simulation ===")
    print(f"Profile: {report.profile}")
    print(f"Since ID: {report.since_id}")
    print(f"Limit: {report.limit if report.limit is not None else 'N/A'}")
    print(f"Velocity filter threshold: {report.velocity_threshold:.8f}")
    print(f"Total cycles: {report.total_cycles}")
    print("")
    print("Regime results:")
    for item in report.regimes:
        result = item.filter_result
        print(
            f"- {item.regime}: "
            f"cycles={item.cycles_count} "
            f"net_no_ext={item.net_profit_without_extreme:+.8f} "
            f"win={item.win_rate * 100:.2f}% "
            f"timeout_losses={item.timeout_losses} "
            f"blocked={result.blocked_cycles} "
            f"blocked_winners={result.blocked_winners} "
            f"blocked_losers={result.blocked_losers} "
            f"kept_net_no_ext={result.net_kept_without_extreme:+.8f} "
            f"improvement={result.net_improvement_vs_baseline:+.8f} "
            f"cycles_day_after={result.cycles_per_day_estimate_after_filter:.2f} "
            f"recommendation={result.recommendation}"
        )
    print("")
    print(f"Best regime: {report.best_regime or 'N/A'}")
    print(f"Conclusion: {report.conclusion}")


def command_extreme_market_discovery(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremeMarketDiscoveryEngine(database).build_report(profile=args.profile)

    print("=== Extreme Market Discovery ===")
    print(f"Profile: {report.profile}")
    print(f"Extreme events: {report.count}")
    print("")
    print("Duration:")
    print(f"- average: {_format_discovery_seconds(report.average_duration_seconds)}")
    print(f"- median: {_format_discovery_seconds(report.median_duration_seconds)}")
    print(f"- longest: {_format_discovery_seconds(report.longest_duration_seconds)}")
    print(f"- shortest: {_format_discovery_seconds(report.shortest_duration_seconds)}")
    print("")
    print("Recovery:")
    print(f"- average: {_format_discovery_seconds(report.average_recovery_seconds)}")
    print(f"- median: {_format_discovery_seconds(report.median_recovery_seconds)}")
    print("")
    print("Distributions:")
    print(f"- amplitude: {_format_hf_regime_counter(report.by_amplitude)}")
    print(f"- session: {_format_hf_regime_counter(report.by_session)}")
    print(f"- hour: {_format_discovery_hour_counter(report.by_hour)}")
    print(f"- clusters: {_format_hf_regime_counter(report.cluster_distribution)}")
    print("")
    print("Frequency:")
    print(f"- average events/day: {report.average_events_per_day:.2f}")
    print(f"- maximum/day: {report.maximum_events_per_day}")
    print(f"- minimum/day: {report.minimum_events_per_day}")
    print("")
    print("Pre-extreme context averages:")
    print(f"- price_velocity: {_format_hf_regime_float(report.average_pre_price_velocity)}")
    print(f"- short_term_drift: {_format_hf_regime_float(report.average_pre_short_term_drift)}")
    print(f"- flat_samples_count: {_format_hf_regime_float(report.average_pre_flat_samples_count)}")
    print(f"- buffer_unique_values: {_format_hf_regime_float(report.average_pre_buffer_unique_values)}")
    print(f"- short_center_distance: {_format_hf_regime_float(report.average_pre_short_center_distance)}")
    print("")
    print("Latest events:")
    for event in report.events[-10:]:
        print(
            f"- db_id={event.db_id} start={event.start_timestamp} end={event.end_timestamp} "
            f"duration={_format_discovery_seconds(event.duration_seconds)} "
            f"session={event.session} close={event.close_price:.8f} "
            f"amplitude={event.amplitude_class} "
            f"max_short_distance={_format_hf_regime_float(event.maximum_short_center_distance)} "
            f"recovery={_format_discovery_seconds(event.recovery_seconds)}"
        )
    print("")
    print(f"Conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")


def command_extreme_replay(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremeReplayEngine(database).build_report(profile=args.profile, output_path=args.output)
    stats = report.statistics

    print("=== Extreme Replay ===")
    print(f"Profile: {report.profile}")
    print(f"Events: {stats.events_count}")
    print(f"Replay scenarios: {stats.scenario_count}")
    print(f"Entered replays: {stats.entered_replays_count}")
    print("")
    print("Replay Statistics:")
    print(f"- average potential profit: {_format_hf_regime_float(stats.average_potential_profit)}")
    print(f"- median potential profit: {_format_hf_regime_float(stats.median_potential_profit)}")
    print(f"- average favorable excursion: {_format_hf_regime_float(stats.average_favorable_excursion)}")
    print(f"- average adverse excursion: {_format_hf_regime_float(stats.average_adverse_excursion)}")
    print(f"- average reward/risk: {_format_hf_regime_float(stats.average_reward_risk)}")
    print(f"- reward/risk distribution: {_format_hf_regime_counter(stats.reward_risk_distribution)}")
    print("")
    print("Latest replay events:")
    for event in report.events[-10:]:
        print(
            f"- event=#{event.event_number} db_id={event.db_id} "
            f"start={event.start_timestamp} end={event.end_timestamp} "
            f"duration={_format_discovery_seconds(event.duration_seconds)} "
            f"session={event.session} cluster={event.cluster_label} "
            f"amplitude={event.amplitude_class}"
        )
        for scenario in event.scenarios:
            if not scenario.entered:
                print(f"  - {scenario.scenario}: skipped ({scenario.skipped_reason})")
                continue
            print(
                f"  - {scenario.scenario}: {scenario.direction} "
                f"MFE={_format_hf_regime_float(scenario.maximum_favorable_excursion)} "
                f"MAE={_format_hf_regime_float(scenario.maximum_adverse_excursion)} "
                f"RR={_format_hf_regime_float(scenario.reward_risk)}"
            )
    print("")
    print(f"Assessment: {stats.assessment}")
    print(f"Report saved: {report.report_path}")


def command_extreme_replay_ranking(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremeReplayRankingEngine(database).build_report(profile=args.profile, output_path=args.output)

    print("=== Extreme Replay Scenario Ranking ===")
    print(f"Profile: {report.profile}")
    print(f"Scenarios ranked: {len(report.scenario_rankings)}")
    print("")
    for item in report.scenario_rankings:
        print(
            f"- {item.scenario_name}: "
            f"events={item.events_count} "
            f"win={item.win_rate * 100:.2f}% "
            f"avg_profit={_format_hf_regime_float(item.average_potential_profit)} "
            f"median_profit={_format_hf_regime_float(item.median_potential_profit)} "
            f"total_profit={item.total_potential_profit:.8f} "
            f"avg_mfe={_format_hf_regime_float(item.average_mfe)} "
            f"avg_mae={_format_hf_regime_float(item.average_mae)} "
            f"worst_mae={_format_hf_regime_float(item.worst_mae)} "
            f"avg_rr={_format_hf_regime_float(item.average_reward_risk)} "
            f"top1_share={item.best_event_contribution_share * 100:.2f}% "
            f"top3_share={item.top3_event_contribution_share * 100:.2f}% "
            f"score={item.stability_score:.2f} "
            f"recommendation={item.recommendation}"
        )
        print(f"  clusters: {_format_hf_regime_counter(item.cluster_breakdown)}")
        print(f"  sessions: {_format_hf_regime_counter(item.session_breakdown)}")
        print(
            f"  recovery avg/median: "
            f"{_format_discovery_seconds(item.average_recovery_seconds)} / "
            f"{_format_discovery_seconds(item.median_recovery_seconds)}"
        )
    print("")
    print(f"Best replay scenario: {report.best_scenario.scenario_name if report.best_scenario else 'N/A'}")
    print(f"Reason: {report.reason}")
    print(f"Report saved: {report.report_path}")


def command_extreme_signal_discovery(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremeSignalDiscoveryEngine(database).build_report(profile=args.profile, output_path=args.output)

    print("=== Extreme Signal Discovery ===")
    print(f"Profile: {report.profile}")
    print(f"Extreme events analyzed: {report.extreme_events_analyzed}")
    print(f"Control windows analyzed: {report.control_windows_analyzed}")
    print(f"Best pre-event window: {report.best_pre_event_window or 'N/A'}s")
    print(
        "Strongest signal candidate: "
        f"{report.strongest_signal_candidate.name if report.strongest_signal_candidate else 'N/A'}"
    )
    print("")
    print("Pre-event window comparison:")
    for comparison in report.window_comparisons:
        print(
            f"- {comparison.window_seconds}s: "
            f"extreme={comparison.extreme_count} "
            f"control={comparison.control_count} "
            f"strongest_metric={comparison.strongest_metric or 'N/A'} "
            f"false_positive_risk={comparison.false_positive_risk * 100:.2f}%"
        )
        top_metrics = sorted(
            comparison.signal_strength.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        for metric, strength in top_metrics:
            print(
                f"  - {metric}: "
                f"ext_avg={_format_hf_regime_float(comparison.extreme_average.get(metric))} "
                f"ctrl_avg={_format_hf_regime_float(comparison.control_average.get(metric))} "
                f"ratio={_format_hf_regime_float(comparison.ratio_extreme_control.get(metric))} "
                f"strength={strength:.2f}"
            )
    print("")
    print("Signal candidates ranking:")
    for candidate in report.signal_candidates:
        print(
            f"- {candidate.name}: "
            f"window={candidate.window_seconds}s "
            f"covered={candidate.extreme_events_covered} "
            f"control_matched={candidate.control_windows_matched} "
            f"precision={candidate.precision_estimate * 100:.2f}% "
            f"recall={candidate.recall_estimate * 100:.2f}% "
            f"false_positive={candidate.false_positive_count} "
            f"score={candidate.signal_score:.2f} "
            f"recommendation={candidate.recommendation}"
        )
    print("")
    print(f"Conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Report saved: {report.report_path}")


def command_extreme_signal_leadtime(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremeSignalLeadTimeEngine(database).build_report(profile=args.profile, output_path=args.output)

    print("=== Extreme Signal Lead Time Analysis ===")
    print(f"Profile: {report.profile}")
    print(f"Extreme events analyzed: {report.extreme_events_analyzed}")
    print(f"Control windows analyzed: {report.control_windows_analyzed}")
    print(f"Best signal: {report.best_signal.signal_name if report.best_signal else 'N/A'}")
    print("")
    print("Lead time matrix:")
    for row in report.lead_time_results:
        print(
            f"- {row.signal_name} @ {row.lead_time_seconds}s: "
            f"detected={row.events_detected} "
            f"rate={row.detection_rate * 100:.2f}% "
            f"false_positive={row.false_positives} "
            f"precision={row.precision * 100:.2f}% "
            f"recall={row.recall * 100:.2f}% "
            f"strength={row.signal_strength:.4f}"
        )
    print("")
    print("Signal ranking:")
    for summary in report.signal_summaries:
        print(
            f"- {summary.signal_name}: "
            f"avg_lead={_format_discovery_seconds(summary.average_lead_time_seconds)} "
            f"median_lead={_format_discovery_seconds(summary.median_lead_time_seconds)} "
            f"best_lead={_format_discovery_seconds(summary.best_lead_time_seconds)} "
            f"worst_lead={_format_discovery_seconds(summary.worst_lead_time_seconds)} "
            f"detection={summary.detection_rate * 100:.2f}% "
            f"false_positive={summary.false_positive_rate * 100:.2f}% "
            f"first_significant={_format_discovery_seconds(summary.first_significant_lead_time_seconds)} "
            f"last_not_visible={_format_discovery_seconds(summary.last_not_visible_lead_time_seconds)} "
            f"score={summary.signal_score:.2f} "
            f"recommendation={summary.recommendation}"
        )
    print("")
    print(f"Final Recommendation: {report.final_recommendation}")
    print(f"Report saved: {report.report_path}")


def command_extreme_paper_signal_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremePaperSignalDiagnosticsEngine(database).build_report(
        profile=args.profile,
        limit=args.limit,
    )

    print("=== Extreme Paper Signal Diagnostics ===")
    print("Diagnostics only. Runtime, real trading, HF v1, and Extreme entry logic are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Total extreme paper cycles: {report.total_cycles}")
    print(f"Target closed: {report.target_closed}")
    print(f"Timeout closed: {report.timeout_closed}")
    print(f"False positives: {report.false_positives}")
    print(f"Lead warning count: {report.lead_warning_count}")
    print(f"Average signal strength winners: {_format_optional_float(report.average_signal_strength_winners)}")
    print(f"Average signal strength losers: {_format_optional_float(report.average_signal_strength_losers)}")
    print(f"Average velocity winners: {_format_optional_float(report.average_velocity_winners)}")
    print(f"Average velocity losers: {_format_optional_float(report.average_velocity_losers)}")
    print(f"Average compression winners: {_format_optional_float(report.average_compression_winners)}")
    print(f"Average compression losers: {_format_optional_float(report.average_compression_losers)}")
    print(f"Recommendation: {report.recommendation}")
    if not report.cycles:
        print("No extreme paper cycles available for this profile.")
        return

    print("--- Cycles ---")
    for cycle in report.cycles:
        print(
            f"db_id={cycle.db_id} | direction={cycle.direction} | "
            f"open={cycle.open_price:.8f} | close={cycle.close_price:.8f} | "
            f"net={cycle.net_profit:+.8f} | reason={cycle.close_reason} | "
            f"opened={cycle.opened_at} | closed={cycle.closed_at or 'OPEN'} | "
            f"holding={_format_optional_seconds(cycle.holding_seconds)}"
        )
        print(
            "  signals: "
            f"session={cycle.session_signal} | velocity={cycle.velocity_spike_signal} | "
            f"compression={cycle.compression_signal} | strength={_format_optional_float(cycle.signal_strength)} | "
            f"lead_warning={cycle.lead_warning} | expected={cycle.expected_direction} | entry={cycle.entry_direction}"
        )
        print(
            "  metrics: "
            f"velocity={_format_optional_float(cycle.velocity_value)} / {_format_optional_float(cycle.velocity_threshold)} | "
            f"compression={_format_optional_float(cycle.compression_score)} / {_format_optional_float(cycle.compression_threshold)} | "
            f"move_5s={_format_optional_float(cycle.movement_5s)} | "
            f"move_15s={_format_optional_float(cycle.movement_15s)} | "
            f"move_30s={_format_optional_float(cycle.movement_30s)} | "
            f"move_60s={_format_optional_float(cycle.movement_60s)}"
        )
        print(
            "  outcome: "
            f"MFE={cycle.max_favorable_excursion:+.8f} | MAE={cycle.max_adverse_excursion:+.8f} | "
            f"target_approached={'yes' if cycle.extreme_target_approached else 'no'} | "
            f"false_positive_category={cycle.false_positive_category}"
        )


def command_extreme_late_entry_diagnostics(args) -> None:
    _config, _logger, database = build_context()
    report = ExtremeLateEntryDiagnosticsEngine(database).build_report(profile=args.profile)

    print("=== Extreme Late Entry Diagnostics ===")
    print("Diagnostics only. HF v1, real trading, and real orders are unchanged.")
    print(f"Profile: {report.profile}")
    print(f"Total cycles: {report.total_cycles}")
    print(f"Late-entry cycles: {len(report.late_entry_cycles)}")
    print(f"Extreme-price entry cycles: {len(report.extreme_price_entry_cycles)}")
    print(f"Total net: {report.total_net:+.8f}")
    print(f"Late-entry loss contribution: {report.late_entry_loss_contribution:+.8f}")
    print(f"Extreme-price entry loss contribution: {report.extreme_price_entry_loss_contribution:+.8f}")
    print(f"Net without late-entry cycles: {report.net_without_late_entry_cycles:+.8f}")
    print(f"Net without extreme-price entries: {report.net_without_extreme_price_entries:+.8f}")
    if report.worst_cycle is not None:
        print(
            "Worst cycle: "
            f"db_id={report.worst_cycle.db_id} "
            f"direction={report.worst_cycle.direction} "
            f"open={report.worst_cycle.open_price:.8f} "
            f"close={report.worst_cycle.close_price:.8f} "
            f"net={report.worst_cycle.net_profit:+.8f} "
            f"reason={report.worst_cycle.close_reason}"
        )
    print(f"Recommendation: {report.recommendation}")

    if report.late_entry_cycles:
        print("--- Late-entry cycles ---")
        for cycle in report.late_entry_cycles:
            print(
                f"db_id={cycle.db_id} direction={cycle.direction} "
                f"open={cycle.open_price:.8f} close={cycle.close_price:.8f} "
                f"net={cycle.net_profit:+.8f} reason={cycle.close_reason} "
                f"lead_warning={cycle.lead_warning} "
                f"extreme_price_entry={'yes' if cycle.opened_on_extreme_price else 'no'} "
                f"velocity={_format_optional_float(cycle.velocity_value)}/"
                f"{_format_optional_float(cycle.velocity_threshold)} "
                f"compression={_format_optional_float(cycle.compression_score)}"
            )

    if report.extreme_price_entry_cycles:
        print("--- Known extreme-price entries ---")
        for cycle in report.extreme_price_entry_cycles:
            print(
                f"db_id={cycle.db_id} direction={cycle.direction} "
                f"open={cycle.open_price:.8f} close={cycle.close_price:.8f} "
                f"net={cycle.net_profit:+.8f} reason={cycle.close_reason}"
            )


def _format_discovery_seconds(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.0f}s"


def _format_discovery_hour_counter(values: dict[int, int]) -> str:
    if not values:
        return "N/A"
    return ", ".join(f"{hour:02d}:00={count}" for hour, count in sorted(values.items()))


def _print_hf_run_regime_series(series) -> None:
    print("")
    print(f"--- {series.label} ---")
    print(f"Since ID: {series.since_id}")
    print(f"Limit: {series.limit if series.limit is not None else 'N/A'}")
    print(f"Cycles count: {series.cycles_count}")
    print(f"Net profit: {series.net_profit:+.8f}")
    print(f"Net profit without extreme: {series.net_profit_without_extreme:+.8f}")
    print(f"Extreme cycles: {series.extreme_cycles_count}")
    print(f"Win rate: {series.win_rate * 100:.2f}%")
    print(f"Win rate without extreme: {series.win_rate_without_extreme * 100:.2f}%")
    print(f"Target closed: {series.target_closed_count}")
    print(f"Timeout closed: {series.timeout_closed_count}")
    print(f"Breakeven: {series.breakeven_count}")
    print(f"Average net: {series.average_net:+.8f}")
    print(f"Median net: {series.median_net:+.8f}")
    print(f"Run duration: {_format_hf_regime_seconds(series.run_duration_seconds)}")
    print(f"Cycles/hour: {series.cycles_per_hour:.2f}")
    print(f"Cycles/day estimate: {series.cycles_per_day_estimate:.2f}")
    print(f"Average holding: {_format_hf_regime_seconds(series.average_holding_seconds)}")
    print(f"Median holding: {_format_hf_regime_seconds(series.median_holding_seconds)}")
    _print_hf_run_direction("BUY", series.buy)
    _print_hf_run_direction("SELL", series.sell)
    print("Entry context:")
    context = series.entry_context
    print(f"- available: {context.available_count}")
    print(f"- missing: {context.missing_count}")
    print(f"- hf_entry_mode distribution: {_format_hf_regime_counter(context.hf_entry_mode_distribution)}")
    print(f"- previous price relation: {_format_hf_regime_counter(context.previous_price_relation_distribution)}")
    print(f"- last different relation: {_format_hf_regime_counter(context.last_different_price_relation_distribution)}")
    print(f"- flat_price_buffer count: {context.flat_price_buffer_count}")
    print(f"- equal center fallback count: {context.equal_center_fallback_count}")
    print(f"- avg short_center distance: {_format_hf_regime_float(context.average_short_center_distance)}")
    print(f"- avg buffer unique values: {_format_hf_regime_float(context.average_price_buffer_unique_values)}")
    print(f"- avg flat samples count: {_format_hf_regime_float(context.average_flat_samples_count)}")
    print(f"- avg price velocity: {_format_hf_regime_float(context.average_price_velocity)}")
    print(f"- avg short-term drift: {_format_hf_regime_float(context.average_short_term_drift)}")
    print(f"- direction confirmed: {context.direction_confirmed_count}")
    print(f"- direction not confirmed: {context.direction_not_confirmed_count}")
    print("Loss diagnostics:")
    loss = series.loss_diagnostics
    print(f"- losing cycles: {loss.losing_cycles_count}")
    print(f"- categories: {_format_hf_regime_counter(loss.categories)}")
    print(f"- no_follow_through: {loss.no_follow_through_count}")
    print(f"- average adverse move: {_format_hf_regime_float(loss.average_adverse_move)}")
    print(f"- average favorable move: {_format_hf_regime_float(loss.average_favorable_move)}")
    print(f"- target touched: {loss.target_touched_count}")
    print(f"- near target: {loss.near_target_count}")
    print(f"- near target samples: {loss.near_target_samples}")


def _print_hf_run_direction(label: str, breakdown) -> None:
    print(
        f"{label}: count={breakdown.count} "
        f"win_rate={breakdown.win_rate * 100:.2f}% "
        f"net={breakdown.net_profit:+.8f} "
        f"timeout_loss={breakdown.timeout_loss_count}"
    )


def _format_hf_regime_counter(values: dict[str, int]) -> str:
    if not values:
        return "N/A"
    return ", ".join(f"{key}={value}" for key, value in sorted(values.items()))


def _format_hf_regime_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.8f}"


def _format_hf_regime_seconds(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.0f}s"


def _print_hf_extreme_cycles(title: str, cycles) -> None:
    print("")
    print(f"{title}:")
    if not cycles:
        print("- none")
        return
    for cycle in cycles:
        print(_format_hf_extreme_cycle(cycle))


def _format_hf_extreme_cycle(cycle) -> str:
    if cycle is None:
        return "- none"
    holding = "N/A" if cycle.holding_seconds is None else f"{cycle.holding_seconds:.0f}s"
    return (
        f"- db_id={cycle.db_id} {cycle.direction} "
        f"net={cycle.net_profit:+.8f} open={cycle.open_price:.8f} "
        f"close={cycle.close_price:.8f} holding={holding} "
        f"reason={cycle.close_reason or 'N/A'} "
        f"extreme_close={str(cycle.is_extreme_close_price).lower()}"
    )


def _format_price_list(prices: list[float]) -> str:
    if not prices:
        return "N/A"
    return ", ".join(f"{price:.8f}" for price in prices)


def _format_optional_price(price: float | None) -> str:
    if price is None:
        return "N/A"
    return f"{price:.8f}"


def _print_hf_profit_audit_cycles(title: str, cycles) -> None:
    print("")
    print(f"{title}:")
    if not cycles:
        print("- none")
        return
    for cycle in cycles:
        print(_format_hf_profit_audit_cycle(cycle))


def _format_hf_profit_audit_cycle(cycle) -> str:
    if cycle is None:
        return "- none"
    issue = f" issue={cycle.issue}" if getattr(cycle, "issue", "") else ""
    distance = abs(float(cycle.close_price) - float(cycle.open_price))
    return (
        f"- db_id={cycle.db_id} {cycle.direction} {cycle.status} "
        f"net={cycle.net_profit:+.8f} qty={cycle.quantity:.8f} "
        f"open={cycle.open_price:.8f} close={cycle.close_price:.8f} "
        f"distance={distance:.8f} reason={cycle.close_reason or 'N/A'}{issue}"
    )


def _print_profile_cycle_summary(cycle) -> None:
    if cycle is None:
        print("- No realized cycles.")
        return
    print(
        f"- db_id={cycle.db_id} direction={cycle.direction} status={cycle.status} "
        f"net_profit={cycle.net_profit:.8f} opened_at={cycle.opened_at} "
        f"closed_at={cycle.closed_at or 'N/A'} close_reason={cycle.close_reason or 'N/A'}"
    )


def _print_profile_breakdown(item) -> None:
    print(
        f"- {item.name}: total={item.total_cycles} automatic={item.automatic_closed_count} "
        f"manual={item.manual_closed_count} open={item.open_count} "
        f"net={item.net_profit:.8f} win_rate={item.win_rate * 100:.2f}%"
    )


def _print_reason_rows(rows: list[tuple[str, int]]) -> None:
    if not rows:
        print("- No data.")
        return

    for reason, count in rows:
        print(f"- {clean_display_text(reason)}: {count}")


def _print_metric_stats(label: str, stats) -> None:
    print(
        f"- {label}: avg={stats.average:.8f} "
        f"min={stats.minimum:.8f} max={stats.maximum:.8f}"
    )


def command_hf_production_readiness(args) -> None:
    config, _logger, database = build_context()
    report = HFProductionReadinessEngine(database, config).build_report(profile=args.profile)

    print("=== HF v1 Production Readiness Audit ===")
    print("Diagnostics only. Real trading remains disabled; no orders are created.")
    print(f"Profile: {report.profile}")
    print(f"Overall status: {report.status}")
    print("")
    print("Checks:")
    for check in report.checks:
        status = "PASS" if check.ok else "FAIL"
        print(f"- [{status}] {check.name}: {check.message}")

    if report.performance_summary is not None:
        summary = report.performance_summary
        print("")
        print("Latest paper performance:")
        print(f"- total cycles: {summary.total_profile_cycles}")
        print(f"- automatic closed: {summary.automatic_closed_count}")
        print(f"- manual closed: {summary.manual_closed_count}")
        print(f"- open: {summary.open_count}")
        print(f"- realized net: {summary.total_realized_net_profit:+.8f}")
        print(f"- win rate: {summary.real_outcome_win_rate * 100:.2f}%")
        print(f"- recommendation: {summary.recommendation}")

    if report.failed_checks:
        print("")
        print("Blocking checks:")
        for check in report.failed_checks:
            print(f"- {check.name}: {check.message}")


def command_hf_real_dry_run(args) -> None:
    config, _logger, _database = build_context()
    report = HFRealDryRunEngine(config).build_report_with_stake(
        profile=args.profile,
        pilot_stake=args.pilot_stake,
    )

    print("=== HF v1 Real Exchange Dry Run ===")
    print("Diagnostics only. Real trading remains disabled; no orders are created.")
    print(f"Profile: {report.profile}")
    print(f"Overall status: {report.status}")
    print("")
    print("Checks:")
    for check in report.checks:
        status = "PASS" if check.ok else "FAIL"
        suffix = f" | warning: {check.warning}" if check.warning else ""
        print(f"- [{status}] {check.name}: {check.message}{suffix}")

    print("")
    print("Proposed sizing:")
    print(f"- stake source: {report.stake_source}")
    print(f"- USDT balance: {_format_decimal_optional(report.usdt_balance)}")
    print(f"- USDC balance: {_format_decimal_optional(report.usdc_balance)}")
    print(f"- stake: {_format_decimal_optional(report.proposed_stake)}")
    print(f"- quantity raw: {_format_decimal_optional(report.proposed_quantity)}")
    print(f"- quantity rounded: {_format_decimal_optional(report.proposed_quantity_rounded)}")
    print(f"- BUY target price: {_format_decimal_optional(report.buy_target_price)}")
    print(f"- SELL target price: {_format_decimal_optional(report.sell_target_price)}")

    if report.warnings:
        print("")
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")

    if report.failed_checks:
        print("")
        print("Blocking checks:")
        for check in report.failed_checks:
            print(f"- {check.name}: {check.message}")


def command_hf_small_real_pilot(args) -> None:
    config, _logger, database = build_context()
    report = HFRealPilotEngine(database, config).run_once(
        profile=args.profile,
        pilot_stake=Decimal(str(args.pilot_stake)),
        confirmed=args.confirm_real_pilot,
        max_cycles_per_run=args.max_cycles_per_run,
    )

    print("=== HF v1 Small Real Pilot ===")
    print("WARNING: This is the only command path allowed to create HF v1 real pilot spot orders.")
    print("Safety gates run before any order attempt.")
    print(f"Profile: {report.profile}")
    print(f"Run ID: {report.run_id}")
    print(f"Overall status: {report.status}")
    print(f"Dry-run status: {report.dry_run_status or 'N/A'}")
    print(f"Order attempted: {'yes' if report.order_attempted else 'no'}")
    print(f"Order status: {report.order_status or 'N/A'}")
    print(f"Real cycle db_id: {report.real_cycle_id or 'N/A'}")
    print(f"Message: {report.message}")
    print("")
    print("Checks:")
    for check in report.checks:
        status = "PASS" if check.ok else "FAIL"
        print(f"- [{status}] {check.name}: {check.message}")

    if report.failed_checks:
        print("")
        print("Blocking checks:")
        for check in report.failed_checks:
            print(f"- {check.name}: {check.message}")


def command_hf_small_real_pilot_watch(args) -> None:
    config, _logger, database = build_context()
    profile = args.profile
    bot = _apply_profile_to_bot(BotEngine(), profile)
    pilot_engine = HFRealPilotEngine(database, config)

    def signal_provider() -> HFRealPilotSignalSnapshot:
        market_state = bot.market_analyzer.analyze_market()
        decision = bot.decision_engine.make_decision(market_state)
        candidate = decision.action in {"BUY_USDC", "SELL_USDC"}
        return HFRealPilotSignalSnapshot(
            price=float(getattr(market_state, "price", 0.0) or 0.0),
            short_center=float(getattr(market_state, "short_center", 0.0) or 0.0),
            hf_entry_mode=str(getattr(market_state, "hf_entry_mode", "N/A")),
            candidate=candidate,
            entry_signal=decision.action if candidate else None,
            block_reason="N/A" if candidate else _collection_entry_block_reason({
                "action": decision.action,
                "reason": decision.reason,
            }),
        )

    def print_update(update) -> None:
        signal = update.signal
        print(
            f"[real-pilot-watch {update.update_number}] "
            f"price={_format_collection_float(signal.price)} | "
            f"short_center={_format_collection_float(signal.short_center)} | "
            f"hf_entry_mode={signal.hf_entry_mode} | "
            f"candidate={'yes' if signal.candidate else 'no'} | "
            f"block={signal.block_reason} | "
            f"open_real={update.open_real_cycles} | "
            f"safety={update.safety_status}"
        )

    print("=== HF v1 Small Real Pilot Watch ===")
    print("WARNING: This command may create at most one SPOT real pilot order after explicit confirmation and safety gates.")
    print(f"Profile: {profile}")
    print(f"Pilot stake: {args.pilot_stake:.8f}")
    print(f"Max iterations: {args.max_iterations}")
    print(f"Interval seconds: {args.interval}")

    report = pilot_engine.watch(
        profile=profile,
        pilot_stake=Decimal(str(args.pilot_stake)),
        confirmed=args.confirm_real_pilot,
        max_iterations=args.max_iterations,
        interval_seconds=args.interval,
        signal_provider=signal_provider,
        update_callback=print_update,
    )

    print("")
    print("=== HF v1 Small Real Pilot Watch Result ===")
    print(f"Status: {report.status}")
    print(f"Iterations: {report.iterations}")
    print(f"Order attempted: {'yes' if report.order_attempted else 'no'}")
    if report.final_pilot_report is not None:
        final = report.final_pilot_report
        print(f"Final dry-run status: {final.dry_run_status or 'N/A'}")
        print(f"Final order status: {final.order_status or 'N/A'}")
        print(f"Final real cycle db_id: {final.real_cycle_id or 'N/A'}")
        print(f"Message: {final.message}")
        if final.failed_checks:
            print("Blocking checks:")
            for check in final.failed_checks:
                print(f"- {check.name}: {check.message}")


def command_hf_real_pilot_status(args) -> None:
    config, _logger, database = build_context()
    report = HFRealPilotEngine(database, config).build_status(args.profile)

    print("=== HF v1 Real Pilot Status ===")
    print(f"Profile: {report.profile}")
    print(f"Status: {report.status}")
    print(f"Open real cycles: {report.open_cycles}")
    print(f"Closed real cycles: {report.closed_cycles}")
    print(f"Net profit: {report.net_profit:+.8f}")
    print(f"Losing cycles: {report.losing_cycles}")
    print(f"Order events: {report.order_events}")
    print(f"Emergency stop: {'yes' if report.emergency_stop else 'no'}")
    if report.open_cycle_details is not None:
        cycle = report.open_cycle_details
        print("")
        print("Open real cycle:")
        print(f"- db_id: {cycle.db_id}")
        print(f"- direction: {cycle.direction}")
        print(f"- open_price: {_format_decimal_optional(cycle.open_price)}")
        print(f"- target_price: {_format_decimal_optional(cycle.target_price)}")
        print(f"- quantity: {_format_decimal_optional(cycle.quantity)}")
        print(f"- opened_at: {cycle.opened_at}")
        print(f"- age_seconds: {cycle.age_seconds:.2f}")
        print(f"- current_price: {_format_decimal_optional(cycle.current_price)}")
        print(f"- unrealized_pnl: {_format_decimal_optional(cycle.unrealized_pnl)}")
        print(f"- distance_to_target: {_format_decimal_optional(cycle.distance_to_target)}")


def command_hf_real_pilot_close_watch(args) -> None:
    config, _logger, database = build_context()
    pilot_engine = HFRealPilotEngine(database, config)

    def print_update(update) -> None:
        print(
            f"[real-pilot-close-watch {update.update_number}] "
            f"price={_format_decimal_optional(update.current_price)} | "
            f"target={_format_decimal_optional(update.target_price)} | "
            f"distance={_format_decimal_optional(update.distance_to_target)} | "
            f"uPnL={_format_decimal_optional(update.unrealized_pnl)} | "
            f"age={update.age_seconds:.2f}s | "
            f"target_met={'yes' if update.close_condition_met else 'no'} | "
            f"timeout_met={'yes' if update.timeout_condition_met else 'no'} | "
            f"close_reason={update.close_reason or 'N/A'}"
        )

    print("=== HF v1 Real Pilot Close Watch ===")
    print("WARNING: This command never opens entries; it may create at most one SPOT close order for an existing real cycle.")
    print(f"Profile: {args.profile}")
    print(f"Max iterations: {args.max_iterations}")
    print(f"Interval seconds: {args.interval}")

    report = pilot_engine.close_watch(
        profile=args.profile,
        confirmed=args.confirm_real_pilot,
        max_iterations=args.max_iterations,
        interval_seconds=args.interval,
        update_callback=print_update,
    )

    print("")
    print("=== HF v1 Real Pilot Close Watch Result ===")
    print(f"Status: {report.status}")
    print(f"Iterations: {report.iterations}")
    print(f"Order attempted: {'yes' if report.order_attempted else 'no'}")
    print(f"Order status: {report.order_status or 'N/A'}")
    print(f"Real cycle db_id: {report.real_cycle_id or 'N/A'}")
    print(f"Close reason: {report.close_reason or 'N/A'}")
    print(f"Message: {report.message}")
    if report.failed_checks:
        print("Blocking checks:")
        for check in report.failed_checks:
            print(f"- {check.name}: {check.message}")


def _format_decimal_optional(value) -> str:
    if value is None:
        return "N/A"
    return f"{value:.8f}"


def command_notifications(args) -> None:
    _config, _logger, database = build_context()
    engine = NotificationEngine(database)

    if args.mark_read:
        engine.mark_all_as_read()
        print("РЈСЃС– РїРѕРІС–РґРѕРјР»РµРЅРЅСЏ РїРѕР·РЅР°С‡РµРЅРѕ СЏРє РїСЂРѕС‡РёС‚Р°РЅС–.")
        return

    notifications = database.load_recent_notifications(limit=args.limit)
    unread = engine.get_unread_count()

    print(f"=== Notifications | unread={unread} ===")
    if not notifications:
        print("РџРѕРІС–РґРѕРјР»РµРЅСЊ РЅРµРјР°С”.")
        return

    for item in notifications:
        status = "read" if item.is_read else "unread"
        cycle = f" | cycle={item.cycle_id}" if item.cycle_id is not None else ""
        print(f"[{item.level.value}] {item.created_at.isoformat()} | {status}{cycle}")
        print(f"{item.title}: {item.message}")
        print("-" * 60)


def command_audit(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_decision_audit(limit=args.limit)

    print("=== Decision Audit ===")
    if not rows:
        print("Audit-Р·Р°РїРёСЃС–РІ РЅРµРјР°С”.")
        return

    for row in rows:
        timestamp, decision, allowed, reason, risk_reason, explanation, cycle_id = row
        print(f"{timestamp} | decision={decision} | allowed={bool(allowed)} | cycle={cycle_id}")
        print(f"Decision reason: {reason}")
        print(f"Risk reason: {risk_reason}")
        print(f"Explanation: {explanation}")
        print("-" * 60)



def command_backtest(args) -> None:
    config, logger, database = build_context()
    provider = BinanceMarketDataProvider(base_url=config.binance_base_url)
    historical = HistoricalDataProvider(provider)

    interval = args.interval or config.backtest_interval
    limit = args.limit or config.backtest_limit
    profile = args.profile
    debug_callback = None
    debug_counter = {"count": 0}
    if args.debug_decisions:
        debug_callback, debug_counter = _build_decision_debug_callback(profile)

    logger.info(
        "CLI backtest command started: symbol=%s interval=%s limit=%s profile=%s",
        config.symbol,
        interval,
        limit,
        profile,
    )

    candles = historical.get_candles(config.symbol, interval, limit)
    backtest_engine = BacktestEngine(
        config,
        decision_engine=_profile_decision_engine(config, profile),
        decision_debug_callback=debug_callback,
    )
    result, trades = backtest_engine.run(candles)
    equity_engine = EquityAnalyticsEngine()
    equity_points = equity_engine.build_equity_points(backtest_engine.last_equity_curve)
    periods = equity_engine.build_period_analytics(backtest_engine.last_equity_curve, trades)
    insights = BacktestInsightsEngine().build_insights(result, periods)
    run_id = database.save_backtest_result(result, trades)
    database.save_backtest_equity_points(run_id, equity_points)
    database.save_backtest_period_analytics(run_id, periods)
    exporter = BacktestReportExporter()
    summary_path = exporter.export_summary_csv(run_id, result, strategy_profile=profile)
    trades_path = exporter.export_trades_csv(run_id, result, trades)
    equity_path = exporter.export_equity_csv(run_id, equity_points)
    periods_path = exporter.export_period_analytics_csv(run_id, periods)
    insights_path = BacktestInsightsExporter().export_txt(run_id, insights)

    print("=== Backtest ===")
    print(f"Run ID: {run_id}")
    print(f"Strategy profile: {profile}")
    print(f"Symbol: {result.symbol}")
    print(f"Interval: {result.interval}")
    print(f"Candles: {result.candles}")
    print(f"Signals: {result.signals}")
    print(f"Trades: {result.trades}")
    print(f"Winning trades: {result.winning_trades}")
    print(f"Losing trades: {result.losing_trades}")
    print(f"Win rate: {result.win_rate * 100:.2f}%")
    print(f"Gross profit: {result.gross_profit:.8f}")
    print(f"Fees: {result.total_fees:.8f}")
    print(f"Net profit: {result.net_profit:.8f}")
    print(f"ROI: {result.roi * 100:.4f}%")
    print(f"Max drawdown: {result.max_drawdown * 100:.4f}%")
    print(f"Sharpe: {result.sharpe_ratio:.4f}")
    print(f"Sortino: {result.sortino_ratio:.4f}")
    print(f"Profit factor: {result.profit_factor:.4f}")
    print(f"Expectancy: {result.expectancy:.8f}")
    print(f"Summary CSV: {summary_path}")
    print(f"Trades CSV: {trades_path}")
    print(f"Equity CSV: {equity_path}")
    print(f"Periods CSV: {periods_path}")
    print(f"Insights TXT: {insights_path}")
    print("--- Insights ---")
    print(f"Rating: {insights.rating}")
    print(f"Summary: {insights.summary}")
    if insights.strengths:
        print("Strengths:")
        for item in insights.strengths:
            print(f"- {item}")
    if insights.weaknesses:
        print("Weaknesses:")
        for item in insights.weaknesses:
            print(f"- {item}")
    if insights.warnings:
        print("Warnings:")
        for item in insights.warnings:
            print(f"- {item}")
    if insights.next_steps:
        print("Next steps:")
        for item in insights.next_steps:
            print(f"- {item}")
    if args.debug_decisions and debug_counter["count"] == 0:
        print("[decision-debug] No potential entry points were evaluated.")


def command_backtest_runs(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_backtest_runs(limit=args.limit)

    print("=== Recent Backtest Runs ===")
    if not rows:
        print("Backtest-Р·Р°РїСѓСЃРєС–РІ С‰Рµ РЅРµРјР°С”.")
        return

    for row in rows:
        run_id, timestamp, symbol, interval, candles, trades, win_rate, net_profit, roi, max_drawdown = row
        print(
            f"#{run_id} | {timestamp} | {symbol} {interval} | "
            f"candles={candles} trades={trades} win_rate={win_rate * 100:.2f}% "
            f"net={net_profit:.8f} roi={roi * 100:.4f}% dd={max_drawdown * 100:.4f}%"
        )


def command_backtest_compare(args) -> None:
    _config, _logger, database = build_context()
    engine = BacktestComparisonEngine(database)
    rows = engine.get_ranked_runs(limit=args.limit)

    print("=== Backtest Comparison ===")
    if not rows:
        print("Backtest-Р·Р°РїСѓСЃРєС–РІ С‰Рµ РЅРµРјР°С”.")
        return

    for rank, row in enumerate(rows, start=1):
        print(
            f"#{rank} | run={row.run_id} | {row.symbol} {row.interval} | "
            f"trades={row.trades} win={row.win_rate * 100:.2f}% "
            f"net={row.net_profit:.8f} roi={row.roi * 100:.4f}% "
            f"dd={row.max_drawdown * 100:.4f}% score={row.score:.4f}"
        )

    if args.export:
        path = BacktestComparisonExporter().export_csv(rows)
        print(f"CSV comparison exported: {path}")


def command_parameter_sweep(args) -> None:
    config, logger, _database = build_context()
    provider = BinanceMarketDataProvider(base_url=config.binance_base_url)
    historical = HistoricalDataProvider(provider)

    interval = args.interval or config.backtest_interval
    limit = args.limit or config.backtest_limit
    target_profits = _parse_float_list(args.target_profits)
    trade_sizes = _parse_float_list(args.trade_sizes)

    logger.info(
        "CLI parameter sweep started: interval=%s limit=%s target_profits=%s trade_sizes=%s",
        interval,
        limit,
        target_profits,
        trade_sizes,
    )

    candles = historical.get_candles(config.symbol, interval, limit)
    results = ParameterSweepEngine(config).run(
        candles=candles,
        target_profits=target_profits,
        trade_size_percents=trade_sizes,
    )

    print("=== Parameter Sweep ===")
    if not results:
        print("Р РµР·СѓР»СЊС‚Р°С‚С–РІ РЅРµРјР°С”.")
        return

    for rank, item in enumerate(results[:args.top], start=1):
        result = item.backtest_result
        print(
            f"#{rank} | target_profit={item.parameters.target_profit} "
            f"trade_size={item.parameters.trade_size_percent} | "
            f"trades={result.trades} win={result.win_rate * 100:.2f}% "
            f"net={result.net_profit:.8f} roi={result.roi * 100:.4f}% "
            f"dd={result.max_drawdown * 100:.4f}% score={item.score:.4f}"
        )

    if args.export:
        path = ParameterSweepExporter().export_csv(results)
        print(f"CSV parameter sweep exported: {path}")


def command_walk_forward(args) -> None:
    config, logger, database = build_context()
    provider = BinanceMarketDataProvider(base_url=config.binance_base_url)
    historical = HistoricalDataProvider(provider)

    interval = args.interval or config.backtest_interval
    limit = args.limit or config.backtest_limit

    candles = historical.get_candles(config.symbol, interval, limit)
    result, windows = WalkForwardEngine(config).run(
        candles=candles,
        target_profits=_parse_float_list(args.target_profits),
        trade_size_percents=_parse_float_list(args.trade_sizes),
        train_size=args.train_size,
        test_size=args.test_size,
    )

    logger.info("Walk-forward executed: windows=%s robustness=%s", result.windows, result.robustness_score)

    run_id = database.save_walk_forward_result(result, windows)

    print("=== Walk Forward ===")
    print(f"Run ID: {run_id}")
    print(f"Windows: {result.windows}")
    print(f"Average test ROI: {result.average_test_roi * 100:.4f}%")
    print(f"Average test win rate: {result.average_test_win_rate * 100:.2f}%")
    print(f"Total test trades: {result.total_test_trades}")
    print(f"Profitable windows: {result.profitable_windows}")
    print(f"Robustness score: {result.robustness_score:.4f}")

    for item in windows:
        print(
            f"Window #{item.window_index}: "
            f"target_profit={item.best_parameters.target_profit} "
            f"trade_size={item.best_parameters.trade_size_percent} | "
            f"test_trades={item.test_result.trades} "
            f"test_roi={item.test_result.roi * 100:.4f}% "
            f"test_score={item.test_score:.4f}"
        )

    if args.export:
        path = WalkForwardExporter().export_csv(result, windows)
        print(f"Walk-forward CSV exported: {path}")


def command_walk_forward_runs(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_walk_forward_runs(limit=args.limit)

    print("=== Recent Walk-Forward Runs ===")
    if not rows:
        print("Walk-forward Р·Р°РїСѓСЃРєС–РІ С‰Рµ РЅРµРјР°С”.")
        return

    for row in rows:
        run_id, timestamp, windows, avg_roi, avg_win, trades, profitable, robustness = row
        print(
            f"#{run_id} | {timestamp} | windows={windows} "
            f"avg_roi={avg_roi * 100:.4f}% avg_win={avg_win * 100:.2f}% "
            f"trades={trades} profitable_windows={profitable} "
            f"robustness={robustness:.4f}"
        )


def command_backtest_periods(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_backtest_period_analytics(args.run_id)

    print(f"=== Backtest Period Analytics | run_id={args.run_id} ===")
    if not rows:
        print("Period analytics РЅРµ Р·РЅР°Р№РґРµРЅРѕ.")
        return

    for period, start_value, end_value, profit, roi, trades in rows:
        print(
            f"{period}: start={start_value:.8f} end={end_value:.8f} "
            f"profit={profit:.8f} roi={roi * 100:.4f}% trades={trades}"
        )


def command_paper_sim(args) -> None:
    config, logger, database = build_context()
    bot = BotEngine()

    portfolio_manager = PaperPortfolioManager(
        initial_usdt=config.backtest_initial_usdt,
        initial_usdc=config.backtest_initial_usdc,
    )
    exchange = PaperExchange(config, portfolio_manager)
    order_manager = PaperOrderManager(config, exchange)

    print("=== Paper Sim ===")

    for index in range(args.iterations):
        market_state = bot.market_analyzer.analyze_market()
        decision = bot.decision_engine.make_decision(market_state)
        portfolio = portfolio_manager.get_portfolio(market_state.price)
        risk = bot.risk_manager.validate_decision(decision, portfolio, current_price=market_state.price)

        print(f"Iteration {index + 1}: price={market_state.price} decision={decision.action} risk={risk.allowed}")

        if risk.allowed:
            execution = order_manager.execute_decision(decision.action, market_state)
            if execution:
                database.save_paper_execution(execution)
                print(
                    f"Paper order {execution.order.status.value}: "
                    f"{execution.order.side.value} qty={execution.order.quantity:.6f} "
                    f"price={execution.order.price:.8f} value={execution.portfolio.total_value:.8f}"
                )

    final_portfolio = portfolio_manager.get_portfolio()
    logger.info("Paper sim completed: value=%s", final_portfolio.total_value)
    print(f"Final USDT: {final_portfolio.usdt:.8f}")
    print(f"Final USDC: {final_portfolio.usdc:.8f}")
    print(f"Final value: {final_portfolio.total_value:.8f}")


def command_paper_orders(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_orders(limit=args.limit)

    print("=== Recent Paper Orders ===")
    if not rows:
        print("Paper orders С‰Рµ РЅРµРјР°С”.")
        return

    for row in rows:
        timestamp, order_id, side, price, quantity, notional, status, reason, fee, usdt, usdc, value = row
        print(
            f"{timestamp} | order={order_id} {side} {status} "
            f"price={price:.8f} qty={quantity:.6f} fee={fee:.8f} "
            f"portfolio={value:.8f} | {reason}"
        )



def command_paper_cycle_sim(args) -> None:
    config, logger, database = build_context()
    profile = args.profile
    _ensure_profile_allowed_for_paper(config, profile)
    bot = _apply_profile_to_bot(BotEngine(), profile)
    debug_callback = None
    debug_counter = {"count": 0}
    if args.debug_decisions:
        debug_callback, debug_counter = _build_decision_debug_callback(profile)
    risk_debug_callback = None
    risk_debug_counter = {"count": 0}
    if args.debug_risk_details:
        risk_debug_callback, risk_debug_counter = _build_risk_profitability_debug_callback(config, database)
    entry_zone_debug_callback = None
    entry_zone_debug_builder = None
    if args.debug_entry_zones:
        entry_zone_debug_callback, entry_zone_debug_builder = _build_entry_zone_debug_callback(config)
    close_debug_callback = None
    close_debug_counter = {"count": 0}
    if args.debug_close:
        close_debug_callback, close_debug_counter = _build_close_debug_callback()
    result = PaperTradingEngine(
        config,
        database,
        bot=bot,
        decision_debug_callback=debug_callback,
        risk_debug_callback=risk_debug_callback,
        entry_zone_debug_callback=entry_zone_debug_callback,
        close_debug_callback=close_debug_callback,
        force_refresh_market_data=args.force_refresh_market_data,
        strategy_profile=profile,
        safe_stop=args.safe_stop,
        resume_recovery_cycles=args.resume_recovery,
    ).run(args.iterations)

    logger.info(
        "Paper cycle sim completed: iterations=%s opened=%s closed=%s safety_stops=%s value=%s profile=%s",
        result.iterations,
        result.opened_cycles,
        result.closed_cycles,
        result.safety_stops,
        result.final_portfolio.total_value,
        profile,
    )

    cycle_rows = database.load_recent_paper_cycles(limit=500)
    safety_rows = database.load_recent_paper_safety_events(limit=500)
    stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)
    insights = PaperInsightsEngine().build(stats, safety_rows)
    paper_run_id = database.save_paper_run(result, insights)
    insights_path = PaperInsightsExporter().export_txt(paper_run_id, insights)
    summary_path = PaperReportExporter().export_summary_csv(stats, strategy_profile=profile)

    PaperTradingCliRenderer().render_paper_cycle_sim(
        result,
        stats,
        insights,
        profile=profile,
        summary_path=summary_path,
        insights_path=insights_path,
    )
    if result.recovery_required:
        PaperTradingCliRenderer().render_recovery_required(result.recovery_message)
    print(f"Paper Run ID: {paper_run_id}")
    if args.debug_entry_zones and entry_zone_debug_builder is not None:
        _print_entry_zone_debug_summary(entry_zone_debug_builder)
    if args.debug_decisions and debug_counter["count"] == 0:
        print("[decision-debug] No potential entry points were evaluated.")
    if args.debug_risk_details and risk_debug_counter["count"] == 0:
        print("[risk-debug] No BUY/SELL risk profitability checks were evaluated.")
    if args.debug_close and close_debug_counter["count"] == 0:
        print("[close-debug] No open paper cycles were evaluated.")


def command_collect_closed_cycles(args) -> None:
    config, logger, database = build_context()
    profile = args.profile
    _ensure_profile_allowed_for_paper(config, profile)

    use_new_target, collection_target = _collection_target_settings(args)
    collection_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    current_session_id = f"collection-{collection_id}"

    if args.interval < 0:
        raise ValueError("--interval must be 0 or greater.")
    if args.max_iterations is not None and args.max_iterations <= 0:
        raise ValueError("--max-iterations must be greater than 0 when provided.")
    if args.print_every <= 0:
        raise ValueError("--print-every must be greater than 0.")
    if args.progress_interval < 0:
        raise ValueError("--progress-interval must be 0 or greater.")

    logger.debug(
        "Closed cycle collection watcher started: profile=%s target=%s interval=%s max_iterations=%s",
        profile,
        args.target,
        args.interval,
        args.max_iterations,
    )

    print("=== Closed Cycles Collection Watch ===")
    print(f"Profile: {profile}")
    baseline = database.load_paper_cycle_collection_baseline(profile)
    baseline_max_id = int(baseline["max_cycle_id"])
    print(f"Collection ID: {collection_id}")
    print(f"Target new closed cycles: {collection_target}")
    print(f"Baseline max paper cycle id: {baseline_max_id}")
    print("Mode: DEMO/PAPER only. Real trading disabled.")
    if args.safe_stop:
        print("Safe stop requested: new paper cycle entries are disabled.")

    recovery_cycle = _find_collection_recovery_cycle(database, current_session_id)
    if recovery_cycle is not None:
        recovery_cycle = _enrich_collection_recovery_cycle(config, database, recovery_cycle)
        PaperTradingCliRenderer().render_recovery_required(
            "Open cycle detected from previous session. Automatic close is disabled. Manual recovery action required.",
            cycle=recovery_cycle,
        )
        return

    stats = database.load_paper_cycle_collection_stats(profile)
    new_stats = _load_new_collection_stats(database, profile, baseline_max_id)
    _print_closed_cycle_collection_summary(
        new_stats,
        lifetime_stats=stats,
        collection_id=collection_id,
        profile=profile,
    )
    if _collection_target_reached(stats, new_stats, collection_target, new_mode=use_new_target):
        print("SUCCESS: target new closed cycles already reached.")
        if args.beep:
            _beep_success()
        return

    bot = _apply_profile_to_bot(BotEngine(), profile)
    cycle_tracking_started_at_by_db_id: dict[int, float] = {}
    iteration = 0
    last_regular_progress_at: float | None = None
    while not _collection_target_reached(stats, new_stats, collection_target, new_mode=use_new_target):
        if args.max_iterations is not None and iteration >= args.max_iterations:
            print("STOPPED: max iterations reached before target closed cycles.")
            break

        iteration += 1
        price_info = _load_collection_price_info(config, database, require_binance=args.require_binance)
        if price_info is None:
            stats = database.load_paper_cycle_collection_stats(profile)
            new_stats = _load_new_collection_stats(database, profile, baseline_max_id)
            progress_label = (
                f"NEW CLOSED {int(new_stats['closed_cycles'])} / {collection_target}"
                if use_new_target
                else f"CLOSED {int(new_stats['closed_cycles'])} / {collection_target}"
            )
            print(
                f"[collection {iteration}] WARNING: Binance price unavailable; "
                "iteration skipped because --require-binance is enabled. "
                f"{progress_label} | "
                f"lifetime closed: {int(stats['closed_cycles'])} | "
                f"open cycles: {int(new_stats['open_cycles'])} | "
                "action_taken: skipped_no_live_price | "
                "entry_attempt: no | "
                "candidate_detected: no | "
                "entry_block_reason: no_signal"
            )
            if args.interval:
                time.sleep(args.interval)
            continue

        before_stats = database.load_paper_cycle_collection_stats(profile)
        entry_debug_items: list[dict] = []
        close_debug_items: list[dict] = []
        result = PaperTradingEngine(
            config,
            database,
            bot=bot,
            entry_zone_debug_callback=entry_debug_items.append,
            close_debug_callback=close_debug_items.append,
            strategy_profile=profile,
            safety_baseline_max_id=baseline_max_id if use_new_target else 0,
            safe_stop=args.safe_stop,
            resume_recovery_cycles=args.resume_recovery,
            session_id=current_session_id,
            cycle_tracking_started_at_by_db_id=cycle_tracking_started_at_by_db_id,
        ).run(1)
        stats = database.load_paper_cycle_collection_stats(profile)
        new_stats = _load_new_collection_stats(database, profile, baseline_max_id)
        action_taken = _collection_action_taken(before_stats, stats, result)
        entry_diagnostics = _collection_entry_diagnostics(
            entry_debug_items,
            fallback_market_state=getattr(bot.market_analyzer, "last_market_state", None),
        )
        if result.safety_stops:
            entry_diagnostics["entry_block_reason"] = "safety_filter"
            _apply_collection_paper_safety_block(
                entry_diagnostics,
                getattr(result, "safety_stop_reason", None),
                getattr(result, "safety_diagnostics", None),
            )
        else:
            _apply_collection_policy_diagnostics(
                entry_diagnostics,
                getattr(result, "safety_diagnostics", None),
            )
            if getattr(result, "safety_diagnostics", None):
                entry_diagnostics["safety_filter_passed"] = "yes"
                entry_diagnostics["paper_safety_state"] = "passed"
        now_monotonic = time.monotonic()
        nearest_open_cycle = _nearest_collection_open_cycle(config, database, profile, price_info[0], price_info[1], price_info[2])
        nearest_open_cycle = _apply_collection_tracking_age(
            nearest_open_cycle,
            cycle_tracking_started_at_by_db_id,
            now_monotonic,
        )
        important_event = (
            action_taken in {"opened", "closed"}
            or result.safety_stops > 0
            or result.recovery_required
            or _collection_target_reached(stats, new_stats, collection_target, new_mode=use_new_target)
        )
        should_print_progress = (
            not args.events_only
            and (
                important_event
                or (
                    _should_print_collection_iteration(iteration, args.print_every)
                    and _should_print_collection_progress(
                        last_regular_progress_at,
                        now_monotonic,
                        args.progress_interval,
                    )
                )
            )
        )
        if args.events_only and important_event:
            _print_closed_cycle_collection_event(
                action_taken=action_taken,
                close_reason=_collection_close_reason(close_debug_items, profile),
                close_debug_items=close_debug_items,
                nearest_open_cycle=nearest_open_cycle,
                result=result,
            )
        if should_print_progress:
            last_closed_cycle = _collection_last_closed_cycle_details(
                database,
                profile,
                close_debug_items,
            ) if action_taken == "closed" else None
            _print_closed_cycle_collection_progress(
                new_stats,
                collection_target,
                iteration=iteration,
                price_info=price_info,
                nearest_open_cycle=nearest_open_cycle,
                action_taken=action_taken,
                close_reason=_collection_close_reason(close_debug_items, profile),
                last_closed_cycle=last_closed_cycle,
                entry_diagnostics=entry_diagnostics,
                new_mode=use_new_target,
                lifetime_stats=stats,
                collection_id=collection_id,
                profile=profile,
                verbose_rich=args.verbose_rich,
            )
            last_regular_progress_at = now_monotonic
        if result.recovery_required:
            PaperTradingCliRenderer().render_recovery_required(result.recovery_message)
            break

        if args.safe_stop and int(stats["open_cycles"]) == 0:
            print("SAFE STOP: no open paper cycles remain. Collection stopped.")
            break

        if _collection_target_reached(stats, new_stats, collection_target, new_mode=use_new_target):
            print("SUCCESS: target new closed cycles reached.")
            _print_closed_cycle_collection_summary(
                new_stats,
                lifetime_stats=stats,
                collection_id=collection_id,
                profile=profile,
            )
            if args.beep:
                _beep_success()
            return

        if args.interval:
            time.sleep(args.interval)


def _print_closed_cycle_collection_progress(
    stats: dict[str, float | int],
    target: int,
    *,
    iteration: int,
    price_info: tuple[float, str, str] | None,
    nearest_open_cycle,
    action_taken: str,
    close_reason: str,
    entry_diagnostics: dict[str, str],
    last_closed_cycle: dict | None = None,
    new_mode: bool = False,
    lifetime_stats: dict[str, float | int] | None = None,
    collection_id: str | int | None = None,
    profile: str | None = None,
    verbose_rich: bool = False,
) -> None:
    renderer = PaperTradingCliRenderer()
    if not verbose_rich:
        renderer.render_collection_progress_compact(
            stats,
            target,
            iteration=iteration,
            price_info=price_info,
            nearest_open_cycle=nearest_open_cycle,
            action_taken=action_taken,
            last_closed_cycle=last_closed_cycle,
            entry_diagnostics=entry_diagnostics,
            lifetime_stats=lifetime_stats,
            collection_id=collection_id,
            tracking_limit_seconds=_collection_max_holding_limit(
                getattr(nearest_open_cycle, "profile", profile or "")
            ) if nearest_open_cycle is not None else None,
        )
        return
    renderer.render_collection_progress(
        stats,
        target,
        iteration=iteration,
        price_info=price_info,
        nearest_open_cycle=nearest_open_cycle,
        action_taken=action_taken,
        close_reason=close_reason,
        entry_diagnostics=entry_diagnostics,
        new_mode=new_mode,
        lifetime_stats=lifetime_stats,
        collection_id=collection_id,
        profile=profile,
    )


def _collection_target_reached(
    stats: dict[str, float | int],
    new_stats: dict[str, float | int] | None,
    target: int,
    *,
    new_mode: bool,
) -> bool:
    progress_stats = new_stats if new_mode and new_stats is not None else stats
    return int(progress_stats["closed_cycles"]) >= target


def _print_closed_cycle_collection_summary(
    stats: dict[str, float | int],
    *,
    lifetime_stats: dict[str, float | int] | None = None,
    collection_id: str | int | None = None,
    profile: str | None = None,
) -> None:
    PaperTradingCliRenderer().render_collection_summary(
        stats,
        lifetime_stats=lifetime_stats,
        collection_id=collection_id,
        profile=profile,
    )


def _load_new_collection_stats(database, profile: str, baseline_max_id: int) -> dict[str, float | int | str]:
    stats = database.load_new_paper_cycle_collection_stats(profile, baseline_max_id)
    return HFCollectionExtremeMetricsEngine(database).enrich_stats(stats, profile, baseline_max_id)


def _collection_target_settings(args) -> tuple[bool, int]:
    if args.target is not None and args.target_new is not None:
        raise ValueError("--target and --target-new cannot be used together.")

    if args.target_new is not None:
        if args.target_new <= 0:
            raise ValueError("--target-new must be greater than 0.")
        return True, int(args.target_new)

    target = 100 if args.target is None else int(args.target)
    if target <= 0:
        raise ValueError("--target must be greater than 0.")
    return True, target


def _find_collection_recovery_cycle(database, current_session_id: str) -> dict | None:
    load_with_recovery = getattr(database, "load_open_paper_cycles_with_recovery", None)
    rows = load_with_recovery(limit=1000) if callable(load_with_recovery) else []
    for row in rows:
        cycle = _collection_recovery_cycle_from_row(row, current_session_id)
        if cycle is None:
            continue
        mark_recovery = getattr(database, "mark_paper_cycle_recovery_required", None)
        if callable(mark_recovery):
            mark_recovery(int(cycle["db_id"]))
            cycle["recovery_status"] = "RECOVERY_REQUIRED"
        return cycle
    return None


def _collection_recovery_cycle_from_row(row: tuple, current_session_id: str) -> dict | None:
    (
        db_id,
        _timestamp,
        cycle_id,
        strategy_profile,
        direction,
        _status,
        open_price,
        target_price,
        quantity,
        _open_fee,
        _close_fee,
        _gross_profit,
        _net_profit,
        opened_at,
        _closed_at,
        opened_session_id,
        recovery_status,
    ) = row
    recovery_status = str(recovery_status or "ACTIVE")
    if opened_session_id == current_session_id:
        return None
    if recovery_status == "RESUME_REQUESTED":
        return None
    return {
        "db_id": int(db_id),
        "cycle_id": int(cycle_id),
        "strategy_profile": str(strategy_profile),
        "direction": str(direction),
        "open_price": float(open_price),
        "target_price": float(target_price),
        "quantity": float(quantity),
        "opened_at": str(opened_at),
        "elapsed": _format_collection_elapsed(opened_at),
        "opened_session_id": opened_session_id or "UNKNOWN",
        "current_session_id": current_session_id,
        "recovery_status": recovery_status,
    }


def _format_collection_elapsed(opened_at: str | None) -> str:
    if not opened_at:
        return "unknown"
    try:
        opened = datetime.fromisoformat(str(opened_at))
    except ValueError:
        return "unknown"
    seconds = max(0, int((datetime.utcnow() - opened).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours}h {remaining_minutes}m"


def _enrich_collection_recovery_cycle(config, database, cycle: dict) -> dict:
    enriched = dict(cycle)
    price_info = _load_recovery_current_price_info(config, database)
    if price_info is None:
        enriched.update({
            "current_price": None,
            "current_price_source": "unavailable",
            "current_price_timestamp": "unavailable",
            "distance_to_target": None,
            "target_status": "unknown",
            "estimated_pnl_now": None,
            "decision_hint": "current price unavailable / choose recovery action manually",
        })
        return enriched

    current_price, source, timestamp = price_info
    target_price = float(cycle["target_price"])
    direction = str(cycle["direction"])
    target_reached = (
        current_price >= target_price
        if direction == "BUY_USDC"
        else current_price <= target_price
    )
    distance_to_target = 0.0 if target_reached else abs(target_price - current_price)
    estimated_pnl = FeeEngine(config).calculate_profit(
        direction=direction,
        open_price=float(cycle["open_price"]),
        close_price=float(current_price),
        quantity=float(cycle["quantity"]),
        use_taker_fee=True,
    ).net_profit
    if target_reached:
        decision_hint = "target reached / resume may close safely"
    elif estimated_pnl < 0:
        decision_hint = "target not reached / estimated loss if closed now"
    elif estimated_pnl > 0:
        decision_hint = "target not reached / estimated profit if closed now"
    else:
        decision_hint = "target not reached / estimated breakeven if closed now"

    enriched.update({
        "current_price": float(current_price),
        "current_price_source": source,
        "current_price_timestamp": timestamp,
        "distance_to_target": distance_to_target,
        "target_status": "reached" if target_reached else "not reached",
        "estimated_pnl_now": float(estimated_pnl),
        "decision_hint": decision_hint,
    })
    return enriched


def _load_recovery_current_price_info(config, database) -> tuple[float, str, str] | None:
    try:
        return _load_binance_paper_price(config)
    except Exception:
        pass
    try:
        with database.connect() as conn:
            row = conn.execute(
                """
                SELECT timestamp, price
                FROM market_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return float(row[1]), "LATEST_MARKET_SNAPSHOT", str(row[0])


def _load_collection_price_info(config, database, *, require_binance: bool) -> tuple[float, str, str] | None:
    if require_binance:
        try:
            return _load_binance_paper_price(config)
        except Exception as exc:
            print(f"WARNING: Binance price fetch failed: {exc}")
            return None
    return _load_current_paper_price(config, database)


def _nearest_collection_open_cycle(config, database, profile: str, current_price: float, source: str, timestamp: str):
    report = PaperOpenCycleDiagnosticsEngine(database, config).build_report(
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
        limit=1000,
    )
    matching = [item for item in report.open_cycles if item.profile == profile]
    if not matching:
        return None
    return min(matching, key=lambda item: abs(item.distance_to_target_percent))


def _apply_collection_tracking_age(open_cycle, tracking_started_at_by_db_id: dict[int, float], now_monotonic: float):
    if open_cycle is None:
        return None
    started_at = tracking_started_at_by_db_id.get(int(open_cycle.db_id))
    if started_at is None:
        return open_cycle
    tracking_age = max(0.0, now_monotonic - started_at)
    try:
        return replace(open_cycle, age_seconds=tracking_age)
    except TypeError:
        setattr(open_cycle, "age_seconds", tracking_age)
        return open_cycle


def _collection_action_taken(before_stats: dict[str, float | int], after_stats: dict[str, float | int], result) -> str:
    if int(after_stats["closed_cycles"]) > int(before_stats["closed_cycles"]):
        return "closed"
    if int(after_stats["open_cycles"]) > int(before_stats["open_cycles"]) or result.opened_cycles > 0:
        return "opened"
    return "waiting"


def _collection_close_reason(close_debug_items: list[dict], profile: str) -> str:
    for item in reversed(close_debug_items):
        if item.get("strategy_profile") != profile:
            continue
        reason = item.get("close_reason")
        if reason:
            return str(reason)
    return "N/A"


def _collection_last_closed_cycle_details(database, profile: str, close_debug_items: list[dict]) -> dict | None:
    close_item = _latest_collection_profile_close_debug(close_debug_items, profile)
    db_id = close_item.get("db_id") if close_item else None
    if db_id is None:
        return None
    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT
                c.id, c.strategy_profile, c.direction, c.open_price, c.close_price,
                c.net_profit, c.close_reason, c.opened_at, c.closed_at,
                d.session_signal, d.velocity_spike_signal, d.compression_signal,
                d.signal_strength, d.lead_warning, d.expected_direction,
                d.entry_direction, d.velocity_value, d.velocity_threshold,
                d.compression_score, d.compression_threshold
            FROM paper_cycles c
            LEFT JOIN hf_paper_cycle_entry_diagnostics d ON d.paper_cycle_id = c.id
            WHERE c.id = ?
            """,
            (int(db_id),),
        ).fetchone()
    if not row:
        return None

    close_reason = str(row[6] or close_item.get("close_reason") or "N/A")
    open_price = _collection_optional_float(row[3])
    close_price = _collection_optional_float(row[4])
    target_price = _collection_optional_float(close_item.get("target_price"))
    net_profit = _collection_optional_float(row[5]) or 0.0
    target_hit = bool(close_item.get("target_close_condition_met")) or "target" in close_reason.lower()
    timeout_hit = bool(close_item.get("max_holding_condition_met")) or "timeout" in close_reason.lower()
    distance_to_target = (
        abs(float(close_price) - float(target_price))
        if close_price is not None and target_price is not None
        else None
    )
    holding_seconds = _collection_optional_float(close_item.get("active_tracking"))
    if holding_seconds is None:
        holding_seconds = _collection_holding_seconds(row[7], row[8])
    breakeven_close = net_profit == 0.0
    detail = {
        "db_id": int(row[0]),
        "profile": str(row[1] or profile),
        "direction": str(row[2] or "N/A"),
        "open_price": open_price,
        "close_price": close_price,
        "target_price": target_price,
        "net_profit": net_profit,
        "close_reason": close_reason,
        "holding_seconds": holding_seconds,
        "target_hit": "yes" if target_hit else "no",
        "timeout_hit": "yes" if timeout_hit else "no",
        "distance_to_target_at_close": distance_to_target,
        "was_extreme_close": "yes" if close_price is not None and is_extreme_close_price(close_price) else "no",
        "breakeven_close": "yes" if breakeven_close else "no",
        "possible_reason": _collection_breakeven_possible_reason(
            open_price=open_price,
            close_price=close_price,
            target_hit=target_hit,
            timeout_hit=timeout_hit,
            breakeven=breakeven_close,
        ),
        "extreme_signal_at_entry": _collection_bool_label(row[9]),
        "entry_velocity_signal": _collection_bool_label(row[10]),
        "entry_compression_signal": _collection_bool_label(row[11]),
        "entry_signal_strength": _collection_optional_float(row[12]),
        "lead_warning": str(row[13] or "N/A"),
        "expected_direction": str(row[14] or "N/A"),
        "entry_direction": str(row[15] or "N/A"),
        "entry_velocity_value": _collection_optional_float(row[16]),
        "entry_velocity_threshold": _collection_optional_float(row[17]),
        "entry_compression_score": _collection_optional_float(row[18]),
        "entry_compression_threshold": _collection_optional_float(row[19]),
    }
    if detail["profile"] == "extreme_strategy_v1" and net_profit <= 0:
        detail["false_positive_hint"] = _collection_extreme_false_positive_hint(detail)
    else:
        detail["false_positive_hint"] = "N/A"
    return detail


def _latest_collection_profile_close_debug(close_debug_items: list[dict], profile: str) -> dict | None:
    for item in reversed(close_debug_items):
        if item.get("strategy_profile") != profile:
            continue
        if item.get("close_attempted") or item.get("close_result") == "CLOSED":
            return item
    return None


def _collection_optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collection_bool_label(value) -> str:
    if value is None:
        return "N/A"
    return "yes" if bool(value) else "no"


def _collection_holding_seconds(opened_at, closed_at) -> float | None:
    if not opened_at or not closed_at:
        return None
    try:
        opened = datetime.fromisoformat(str(opened_at))
        closed = datetime.fromisoformat(str(closed_at))
    except ValueError:
        return None
    return max(0.0, (closed - opened).total_seconds())


def _collection_breakeven_possible_reason(
    *,
    open_price: float | None,
    close_price: float | None,
    target_hit: bool,
    timeout_hit: bool,
    breakeven: bool,
) -> str:
    if not breakeven:
        return "N/A"
    if open_price is not None and close_price is not None and abs(open_price - close_price) <= 0.00000001:
        return "timeout_at_entry_price" if timeout_hit else "price_unchanged"
    if target_hit:
        return "rounding_to_tick"
    if not target_hit:
        return "target_not_reached"
    return "unknown"


def _collection_extreme_false_positive_hint(detail: dict) -> str:
    velocity = detail.get("entry_velocity_value")
    threshold = detail.get("entry_velocity_threshold")
    compression = detail.get("entry_compression_score")
    compression_threshold = detail.get("entry_compression_threshold") or 60.0
    if velocity is None or threshold is None or compression is None:
        return "unknown"
    if abs(float(velocity)) <= abs(float(threshold)) * 1.5:
        return "weak_velocity_spike"
    if str(detail.get("lead_warning", "")).lower() == "yes":
        return "late_entry"
    if float(compression) >= float(compression_threshold) and detail.get("target_hit") == "no":
        return "compression_without_breakout"
    direction = detail.get("direction")
    open_price = detail.get("open_price")
    close_price = detail.get("close_price")
    if open_price is not None and close_price is not None:
        moved_against = close_price < open_price if direction == "BUY_USDC" else close_price > open_price
        if moved_against:
            return "wrong_direction"
    return "insufficient_follow_through"


def _collection_entry_diagnostics(entry_debug_items: list[dict], fallback_market_state=None) -> dict[str, str]:
    diagnostics = {
        "entry_attempt": "no",
        "candidate_detected": "no",
        "entry_block_reason": "no_signal",
        "short_center": "N/A",
        "short_center_samples": "N/A",
        "short_center_ready": "N/A",
        "hf_entry_mode": "N/A",
        "previous_price": "N/A",
        "last_different_price": "N/A",
        "price_buffer_unique_values": "N/A",
        "flat_samples_count": "N/A",
        "flat_price_buffer": "N/A",
        "entry_direction": "N/A",
        "target_price": "N/A",
        "target_distance": "N/A",
        "safety_filter_passed": "N/A",
        "safety_block_reason": "N/A",
        "safety_block_details": "N/A",
        "paper_safety_state": "N/A",
        "paper_safety_policy": "N/A",
        "safety_window_scope": "N/A",
        "safety_window_cycles": "N/A",
        "safety_consecutive_losses": "N/A",
        "safety_realized_drawdown": "N/A",
        "safety_timeout_loss_rate": "N/A",
        "safety_min_cycles_met": "N/A",
        "balance_check_passed": "N/A",
        "spread_check_passed": "N/A",
        "cooldown_check_passed": "N/A",
        "open_cycle_check_passed": "N/A",
        "duplicate_entry_check_passed": "N/A",
        "max_open_cycles_check_passed": "N/A",
        "stale_price_check_passed": "N/A",
    }
    if not entry_debug_items:
        if fallback_market_state is not None:
            _apply_collection_short_center_diagnostics(diagnostics, fallback_market_state)
        return diagnostics

    item = entry_debug_items[-1]
    action = item.get("action", "WAIT")
    candidate_detected = action in {"BUY_USDC", "SELL_USDC"}
    order_attempted = bool(item.get("order_attempted", False))
    market_state = item.get("market_state")

    diagnostics["entry_attempt"] = "yes" if order_attempted else "no"
    diagnostics["candidate_detected"] = "yes" if candidate_detected else "no"
    diagnostics["entry_block_reason"] = _collection_entry_block_reason(item)
    _apply_collection_safety_diagnostics(diagnostics, item)
    if market_state is not None:
        _apply_collection_short_center_diagnostics(diagnostics, market_state)
        if diagnostics["entry_block_reason"] == "equal_center_last_different_fallback":
            diagnostics["hf_entry_mode"] = "equal_center_last_different_fallback"
        elif diagnostics["entry_block_reason"] == "flat_price_buffer":
            diagnostics["hf_entry_mode"] = "flat_no_trade"
        elif candidate_detected and not hasattr(market_state, "extreme_signal_detected"):
            diagnostics["hf_entry_mode"] = "short_center_direct"
        price = getattr(market_state, "price", None)
        diagnostics["entry_direction"] = action if candidate_detected else "N/A"
        if candidate_detected and price is not None:
            target_profit = float(item.get("target_profit", 0.0) or 0.0)
            target_price = (
                price * (1.0 + target_profit)
                if action == "BUY_USDC"
                else price * (1.0 - target_profit)
            )
            diagnostics["target_price"] = _format_collection_float(target_price)
            diagnostics["target_distance"] = _format_collection_float(abs(target_price - price))
    return diagnostics


def _apply_collection_short_center_diagnostics(diagnostics: dict[str, str], market_state) -> None:
    short_center = getattr(market_state, "short_center", None)
    samples = getattr(market_state, "hf_short_center_samples", None)
    ready = getattr(market_state, "hf_short_center_ready", None)
    diagnostics["short_center"] = _format_collection_float(short_center)
    diagnostics["short_center_samples"] = "N/A" if samples is None else str(samples)
    diagnostics["short_center_ready"] = "N/A" if ready is None else ("yes" if ready else "no")
    diagnostics["hf_entry_mode"] = str(getattr(market_state, "hf_entry_mode", "N/A"))
    diagnostics["previous_price"] = _format_collection_float(getattr(market_state, "hf_previous_price", None))
    diagnostics["last_different_price"] = _format_collection_float(
        getattr(market_state, "hf_last_different_price", None)
    )
    unique_values = getattr(market_state, "hf_price_buffer_unique_values", None)
    flat_samples = getattr(market_state, "hf_flat_samples_count", None)
    flat_buffer = getattr(market_state, "hf_flat_price_buffer", None)
    diagnostics["price_buffer_unique_values"] = "N/A" if unique_values is None else str(unique_values)
    diagnostics["flat_samples_count"] = "N/A" if flat_samples is None else str(flat_samples)
    diagnostics["flat_price_buffer"] = (
        "N/A" if flat_buffer is None else ("yes" if bool(flat_buffer) else "no")
    )
    if ready is False:
        diagnostics["entry_block_reason"] = "no_short_center"
    _apply_collection_extreme_signal_diagnostics(diagnostics, market_state)


def _apply_collection_extreme_signal_diagnostics(diagnostics: dict[str, str], market_state) -> None:
    if not hasattr(market_state, "extreme_signal_detected"):
        return
    signal_detected = bool(getattr(market_state, "extreme_signal_detected", False))
    session_signal = bool(getattr(market_state, "extreme_session_signal", False))
    velocity_signal = bool(getattr(market_state, "extreme_velocity_spike_signal", False))
    compression_signal = bool(getattr(market_state, "extreme_compression_signal", False))
    diagnostics["hf_entry_mode"] = "extreme_immediate_entry" if signal_detected else "extreme_watch"
    diagnostics["extreme_signal_detected"] = "yes" if signal_detected else "no"
    diagnostics["session_signal"] = "yes" if session_signal else "no"
    diagnostics["velocity_spike_signal"] = "yes" if velocity_signal else "no"
    diagnostics["compression_signal"] = "yes" if compression_signal else "no"
    diagnostics["lead_time_warning"] = str(getattr(market_state, "extreme_lead_time_warning", "N/A"))
    diagnostics["signal_strength"] = _format_collection_float(getattr(market_state, "extreme_signal_strength", None))
    diagnostics["expected_direction"] = str(getattr(market_state, "extreme_expected_direction", "N/A"))
    diagnostics["price_velocity_direction"] = str(getattr(market_state, "extreme_price_velocity_direction", "N/A"))
    diagnostics["price_velocity"] = _format_collection_float(getattr(market_state, "extreme_price_velocity", None))
    diagnostics["velocity_threshold"] = _format_collection_float(getattr(market_state, "extreme_velocity_threshold", None))
    diagnostics["compression_score"] = _format_collection_float(getattr(market_state, "extreme_compression_score", None))
    diagnostics["compression_threshold"] = _format_collection_float(
        getattr(market_state, "extreme_compression_threshold", 60.0)
    )
    diagnostics["extreme_price_guard"] = "yes" if bool(getattr(market_state, "extreme_price_guard", False)) else "no"
    diagnostics["excessive_velocity_guard"] = (
        "yes" if bool(getattr(market_state, "extreme_excessive_velocity_guard", False)) else "no"
    )
    diagnostics["distance_from_center"] = _format_collection_float(
        getattr(market_state, "extreme_distance_from_center", None)
    )
    diagnostics["max_allowed_distance"] = _format_collection_float(
        getattr(market_state, "extreme_max_allowed_distance", None)
    )
    diagnostics["post_extreme_rebound_risk"] = (
        "yes" if bool(getattr(market_state, "extreme_post_rebound_risk", False)) else "no"
    )
    diagnostics["short_center_samples"] = str(getattr(market_state, "extreme_samples", "N/A"))
    diagnostics["price_buffer_unique_values"] = str(getattr(market_state, "extreme_price_buffer_unique_values", "N/A"))
    diagnostics["flat_samples_count"] = str(getattr(market_state, "extreme_flat_samples_count", "N/A"))
    diagnostics["max_holding"] = _format_collection_float(getattr(market_state, "extreme_max_holding_seconds", None))


def _apply_collection_paper_safety_block(
    diagnostics: dict[str, str],
    reason: str | None,
    policy_diagnostics: dict[str, str] | None = None,
) -> None:
    details = str(reason or "Paper safety stopped this iteration.")
    diagnostics["safety_filter_passed"] = "no"
    diagnostics["paper_safety_state"] = "blocked"
    diagnostics["safety_block_reason"] = _classify_paper_safety_reason(details)
    diagnostics["safety_block_details"] = details
    _apply_collection_policy_diagnostics(diagnostics, policy_diagnostics)


def _apply_collection_policy_diagnostics(
    diagnostics: dict[str, str],
    policy_diagnostics: dict[str, str] | None,
) -> None:
    if not policy_diagnostics:
        return
    for key in (
        "paper_safety_policy",
        "safety_window_scope",
        "safety_window_cycles",
        "safety_consecutive_losses",
        "safety_realized_drawdown",
        "safety_timeout_loss_rate",
        "safety_worst_loss",
        "safety_min_cycles_met",
    ):
        diagnostics[key] = str(policy_diagnostics.get(key, "N/A"))


def _apply_collection_safety_diagnostics(diagnostics: dict[str, str], item: dict) -> None:
    action = str(item.get("action", "WAIT"))
    reason = str(item.get("reason", ""))
    risk_reason = str(item.get("risk_reason", ""))
    risk_allowed = bool(item.get("risk_allowed", False))
    entry_block_reason = diagnostics.get("entry_block_reason", "no_signal")

    if entry_block_reason == "existing_cycle":
        diagnostics["safety_filter_passed"] = "no"
        diagnostics["safety_block_reason"] = "existing_cycle"
        diagnostics["safety_block_details"] = reason or risk_reason or "A paper cycle is already open."
        diagnostics["open_cycle_check_passed"] = "no"
        diagnostics["duplicate_entry_check_passed"] = "no"
        diagnostics["max_open_cycles_check_passed"] = "no"
        return

    if action in {"BUY_USDC", "SELL_USDC"} and risk_allowed:
        diagnostics["safety_filter_passed"] = "yes"
        diagnostics["paper_safety_state"] = "passed"
        diagnostics["balance_check_passed"] = "yes"
        diagnostics["open_cycle_check_passed"] = "yes"
        diagnostics["duplicate_entry_check_passed"] = "yes"
        diagnostics["max_open_cycles_check_passed"] = "yes"
        if reason:
            diagnostics["spread_check_passed"] = "yes" if "spread invalid" not in reason.lower() else "no"
        return

    if entry_block_reason != "safety_filter":
        return

    details = risk_reason or reason or "Safety filter blocked entry."
    diagnostics["safety_filter_passed"] = "no"
    diagnostics["paper_safety_state"] = "passed"
    diagnostics["safety_block_details"] = details

    block_reason = _classify_collection_safety_block(reason, risk_reason)
    diagnostics["safety_block_reason"] = block_reason
    if block_reason == "spread_invalid":
        diagnostics["spread_check_passed"] = "no"
    elif block_reason in {"balance_or_reserve_check_failed", "budget_missing"}:
        diagnostics["balance_check_passed"] = "no"


def _classify_collection_safety_block(reason: str, risk_reason: str) -> str:
    text = f"{reason} {risk_reason}".lower()
    if "spread invalid" in text:
        return "spread_invalid"
    if "market health invalid" in text or "market health unhealthy" in text:
        return "market_health_invalid"
    if "abnormal market regime" in text:
        return "abnormal_market_regime"
    if "extreme volatility" in text:
        return "extreme_volatility"
    if "budget" in text or "бюдж" in text:
        return "budget_missing"
    if "reserve" in text or "резерв" in text:
        return "balance_or_reserve_check_failed"
    if "notional" in text:
        return "min_notional_failed"
    if "profit" in text or "прибут" in text or "rounding" in text:
        return "risk_profitability_failed"
    return "risk_manager_or_profile_safety"


def _classify_paper_safety_reason(reason: str) -> str:
    text = reason.lower()
    if "drawdown" in text:
        return "paper_max_drawdown"
    if "portfolio" in text or "value" in text or "мінім" in text:
        return "paper_min_portfolio_value"
    if "cycles" in text or "cycle" in text:
        return "paper_max_losing_cycles"
    return "paper_safety_blocked"


def _collection_entry_block_reason(item: dict) -> str:
    action = item.get("action", "WAIT")
    reason = str(item.get("reason", "")).lower()
    risk_reason = str(item.get("risk_reason", "")).lower()

    if "already open" in reason:
        return "existing_cycle"
    if "no_short_center" in reason:
        return "no_short_center"
    if "flat_price_buffer" in reason:
        return "flat_price_buffer"
    if "equal_center_last_different_fallback" in reason:
        return "equal_center_last_different_fallback"
    if "price_equals_short_center" in reason:
        return "price_equals_short_center"
    if "session_signal_missing" in reason:
        return "outside_session"
    if "velocity_spike_missing" in reason:
        return "velocity_spike_missing"
    if "compression_missing" in reason:
        return "compression_missing"
    if "extreme_price_entry_blocked" in reason:
        return "extreme_price_entry_blocked"
    if "excessive_velocity_entry_blocked" in reason:
        return "excessive_velocity_entry_blocked"
    if "post_extreme_rebound_risk" in reason:
        return "post_extreme_rebound_risk"
    if "too_far_from_center" in reason:
        return "too_far_from_center"
    if "no_extreme_signal" in reason or "no_signal_direction" in reason:
        return "no_signal"
    if "invalid_price" in reason:
        return "invalid_price"
    if "outside new_york session" in reason:
        return "outside_session"
    if "price outside entry zones" in reason or "working corridor center" in reason:
        return "no_entry_zone"
    if "micro trend not confirmed" in reason:
        return "micro_trend_not_confirmed"
    if (
        "spread invalid" in reason
        or "market health invalid" in reason
        or "abnormal market regime" in reason
        or "extreme volatility" in reason
        or "market health unhealthy" in reason
    ):
        return "safety_filter"
    if action in {"BUY_USDC", "SELL_USDC"} and not bool(item.get("risk_allowed", False)):
        return "safety_filter"
    if risk_reason and risk_reason not in {"risk check skipped while database cycle is open", "risk check skipped while active cycle is open"}:
        return "safety_filter"
    if "low center confidence" in reason or "low market activity" in reason or "insufficient cycle prediction score" in reason:
        return "profile_filter"
    if action in {"WAIT", "SAFE_WAIT"} and reason:
        return "profile_filter"
    return "no_signal"


def _should_print_collection_iteration(iteration: int, print_every: int) -> bool:
    return print_every <= 1 or iteration % print_every == 0


def _should_print_collection_progress(
    last_printed_at: float | None,
    now: float,
    progress_interval: float,
) -> bool:
    if last_printed_at is None:
        return True
    return (now - last_printed_at) >= progress_interval


def _print_closed_cycle_collection_event(
    *,
    action_taken: str,
    close_reason: str,
    close_debug_items: list[dict],
    nearest_open_cycle,
    result,
) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    if getattr(result, "recovery_required", False):
        print(f"{timestamp} RECOVERY REQUIRED automatic_close=disabled")
        return
    if getattr(result, "safety_stops", 0):
        reason = getattr(result, "safety_stop_reason", None) or "safety_filter"
        print(f"{timestamp} SAFETY BLOCK reason={reason}")
        return
    if action_taken == "opened" and nearest_open_cycle is not None:
        print(
            f"{timestamp} OPEN {getattr(nearest_open_cycle, 'direction', 'N/A')} "
            f"db_id={getattr(nearest_open_cycle, 'db_id', 'N/A')} "
            f"price={_format_collection_float(getattr(nearest_open_cycle, 'open_price', None))} "
            f"target={_format_collection_float(getattr(nearest_open_cycle, 'target_price', None))}"
        )
        return
    if action_taken == "closed":
        item = _latest_collection_close_debug(close_debug_items)
        reason = close_reason or "N/A"
        label = "TARGET" if reason == "target" else "TIMEOUT" if "holding" in reason or "timeout" in reason else reason.upper()
        db_id = item.get("db_id", "N/A") if item else "N/A"
        print(f"{timestamp} CLOSE {label} db_id={db_id}")


def _latest_collection_close_debug(close_debug_items: list[dict]) -> dict | None:
    for item in reversed(close_debug_items):
        if item.get("close_attempted") or item.get("close_result") == "CLOSED":
            return item
    return close_debug_items[-1] if close_debug_items else None


def _format_collection_float(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.8f}"


def _collection_max_holding_limit(profile: str) -> float | None:
    if profile == "mean_reversion_hf_micro_v1":
        return 270.0
    if profile == "extreme_strategy_v1":
        return EXTREME_MAX_HOLDING_SECONDS
    return None


def _collection_max_holding_condition_met(open_cycle) -> bool:
    limit = _collection_max_holding_limit(open_cycle.profile)
    if limit is None:
        return False
    return _collection_cycle_age_seconds(open_cycle) >= limit


def _collection_cycle_age_seconds(open_cycle) -> float:
    try:
        return max(0.0, float(getattr(open_cycle, "age_seconds", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _beep_success() -> None:
    try:
        import winsound

        for _ in range(3):
            winsound.Beep(1200, 250)
    except Exception:
        for _ in range(3):
            print("\a", end="", flush=True)
        print()


def command_long_paper_run(args) -> None:
    config, logger, database = build_context()
    profile = args.profile
    _ensure_profile_allowed_for_paper(config, profile)
    logger.info(
        "Long paper run started: iterations=%s interval=%s profile=%s",
        args.iterations,
        args.interval,
        profile,
    )
    close_debug_callback = None
    close_debug_counter = {"count": 0}
    if args.debug_close:
        close_debug_callback, close_debug_counter = _build_close_debug_callback()
    result = LongPaperRunWorkflow(config, database).run(
        iterations=args.iterations,
        interval_seconds=args.interval,
        strategy_profile=profile,
        close_debug_callback=close_debug_callback,
    )

    print("=== Long Paper Run ===")
    print("Long paper run completed. Real trading disabled.")
    print(f"Strategy profile: {result.strategy_profile}")
    print(f"Long Run ID: {result.long_run_id}")
    print(f"Paper Run ID: {result.run_id}")
    print(f"Iterations: {result.run_result.iterations}")
    print(f"Opened cycles: {result.run_result.opened_cycles}")
    print(f"Closed cycles: {result.run_result.closed_cycles}")
    print(f"Safety stops: {result.run_result.safety_stops}")
    print(f"Final value: {result.run_result.final_portfolio.total_value:.8f}")
    print("--- Paper Stats ---")
    print(f"Total cycles: {result.stats.total_cycles}")
    print(f"Closed cycles: {result.stats.closed_cycles}")
    print(f"Win rate: {result.stats.win_rate * 100:.2f}%")
    print(f"Net profit: {result.stats.net_profit:.8f}")
    print(f"Profit factor: {result.stats.profit_factor:.4f}")
    print("--- Paper Insights ---")
    print(f"Rating: {result.insights.rating}")
    print(f"Summary: {result.insights.summary}")
    if result.insights.warnings:
        print("Warnings:")
        for item in result.insights.warnings:
            print(f"- {item}")
    if result.insights.next_steps:
        print("Next steps:")
        for item in result.insights.next_steps:
            print(f"- {item}")
    print("--- Validation Summary ---")
    print(f"Overall status: {result.validation_summary.overall_status}")
    print("Warnings:")
    if result.validation_summary.warnings:
        for item in result.validation_summary.warnings:
            print(f"- {item}")
    else:
        print("- None")
    print("Next action:")
    print(result.validation_summary.next_action)
    pressure = OrderBookDiagnosticsEngine(database, config).build_summary()
    print("--- Order Book Pressure Summary ---")
    print("Order book pressure distribution:")
    _print_distribution(pressure.order_book_pressure_distribution)
    print("Entry-zone pressure distribution:")
    _print_distribution(_merge_distributions(pressure.buy_zone_distribution, pressure.sell_zone_distribution))
    print("BUY-zone pressure distribution:")
    _print_distribution(pressure.buy_zone_distribution)
    print("SELL-zone pressure distribution:")
    _print_distribution(pressure.sell_zone_distribution)
    current_price, current_price_source, current_price_timestamp = _load_current_paper_price(config, database)
    open_cycles_report = PaperOpenCycleDiagnosticsEngine(database, config).build_report(
        current_price=current_price,
        current_price_source=current_price_source,
        current_price_timestamp=current_price_timestamp,
        limit=100,
    )
    _print_open_cycles_summary(open_cycles_report)
    print("--- Reports ---")
    print(f"Cycles CSV: {result.report_paths.cycles_csv}")
    print(f"Safety CSV: {result.report_paths.safety_csv}")
    print(f"Summary CSV: {result.report_paths.summary_csv}")
    print(f"Insights TXT: {result.report_paths.insights_txt}")
    if args.debug_close and close_debug_counter["count"] == 0:
        print("[close-debug] No open paper cycles were evaluated.")


def _merge_distributions(*items: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def _print_distribution(distribution: dict[str, int]) -> None:
    if not distribution:
        print("- No data")
        return
    for label, count in distribution.items():
        print(f"- {label}: {count}")


def command_long_paper_runs(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_long_paper_runs(limit=args.limit)

    print("=== Recent Long Paper Runs ===")
    if not rows:
        print("Long paper runs not found yet.")
        return

    for row in rows:
        (
            run_id,
            timestamp,
            iterations,
            interval_seconds,
            final_value,
            net_profit,
            win_rate,
            profit_factor,
            validation_status,
            insights_rating,
            summary_report_path,
        ) = row
        print(
            f"#{run_id} | {timestamp} | iter={iterations} interval={interval_seconds}s | "
            f"value={final_value:.8f} net={net_profit:.8f} win={win_rate * 100:.2f}% "
            f"pf={profit_factor:.4f} validation={validation_status} "
            f"insights={insights_rating} summary={summary_report_path}"
        )


def command_paper_cycles(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_cycles_with_identity(limit=args.limit)

    print("=== Recent Paper Cycles ===")
    if not rows:
        print("Paper cycles С‰Рµ РЅРµРјР°С”.")
        return

    for row in rows:
        db_id, timestamp, cycle_id, strategy_profile, direction, status, open_price, close_price, quantity, open_fee, close_fee, gross, net = row
        print(
            f"{timestamp} | db_id={db_id} cycle_id={cycle_id} profile={strategy_profile} {direction} {status} "
            f"open={open_price:.8f} close={close_price:.8f} "
            f"qty={quantity:.6f} net={net:.8f}"
        )


def command_paper_open_cycles(args) -> None:
    config, _logger, database = build_context()
    current_price, source, timestamp = _load_current_paper_price(config, database)
    report = PaperOpenCycleDiagnosticsEngine(database, config).build_report(
        current_price=current_price,
        current_price_source=source,
        current_price_timestamp=timestamp,
        limit=args.limit,
    )

    print("=== Paper Open Cycles ===")
    print(f"Current price: {report.current_price:.8f}")
    print(f"Current price source: {report.current_price_source}")
    print(f"Current price timestamp: {report.current_price_timestamp}")
    print(f"Open cycles count: {report.open_cycles_count}")
    if not report.open_cycles:
        print("No open paper cycles.")
        return

    for item in report.open_cycles:
        close_status = "yes" if item.close_condition_met else "no"
        print(
            f"db_id={item.db_id} | cycle_id={item.cycle_id} | profile={item.profile} | "
            f"direction={item.direction} | opened_at={item.opened_at} | "
            f"age_seconds={item.age_seconds:.0f}"
        )
        print(
            f"  open_price={item.open_price:.8f} | "
            f"target_price={item.target_price:.8f} | "
            f"current_price={item.current_price:.8f}"
        )
        print(
            f"  distance_to_target={item.distance_to_target:.8f} | "
            f"distance_to_target_percent={item.distance_to_target_percent:.5f}% | "
            f"unrealized_pnl={item.unrealized_pnl:.8f}"
        )
        print(
            f"  close_epsilon={item.close_epsilon:.8f} | "
            f"effective_buy_close_price={item.effective_buy_close_price:.8f} | "
            f"effective_sell_close_price={item.effective_sell_close_price:.8f}"
        )
        print(f"  close_condition_met: {close_status}")
        print(f"  reason_not_closed: {item.reason_not_closed}")


def command_paper_close_cycle(args) -> None:
    config, _logger, database = build_context()
    row = database.load_open_paper_cycle_by_id(args.db_id)
    if row is None:
        raise ValueError(f"OPEN paper cycle not found for db_id={args.db_id}.")

    (
        db_id,
        _timestamp,
        cycle_id,
        strategy_profile,
        direction,
        status,
        open_price,
        _target_price,
        quantity,
        _open_fee,
        _close_fee,
        _gross_profit,
        _net_profit,
        opened_at,
        _closed_at,
    ) = row

    close_price, source, closed_at = _load_binance_paper_price(config)
    profit = FeeEngine(config).calculate_profit(
        direction=str(direction),
        open_price=float(open_price),
        close_price=float(close_price),
        quantity=float(quantity),
        use_taker_fee=True,
    )
    updated = database.close_paper_cycle_manually(
        db_id=int(db_id),
        close_price=float(close_price),
        close_fee=float(profit.fees.close_fee),
        gross_profit=float(profit.gross_profit),
        net_profit=float(profit.net_profit),
        close_reason=str(args.reason),
        closed_at=closed_at,
    )
    if not updated:
        raise ValueError(f"OPEN paper cycle not found for db_id={args.db_id}.")

    print("=== Paper Close Cycle ===")
    print(f"db_id: {db_id}")
    print(f"cycle_id: {cycle_id}")
    print(f"profile: {strategy_profile}")
    print(f"direction: {direction}")
    print(f"previous_status: {status}")
    print("status: CLOSED_MANUAL")
    print(f"reason: {args.reason}")
    print(f"opened_at: {opened_at}")
    print(f"closed_at: {closed_at}")
    print(f"price_source: {source}")
    print(f"open_price: {float(open_price):.8f}")
    print(f"close_price: {float(close_price):.8f}")
    print(f"quantity: {float(quantity):.8f}")
    print(f"gross_profit: {profit.gross_profit:.8f}")
    print(f"close_fee: {profit.fees.close_fee:.8f}")
    print(f"net_profit: {profit.net_profit:.8f}")


def command_paper_recovery_action(args) -> None:
    _config, _logger, database = build_context()
    db_id = _resolve_paper_recovery_db_id(database, args.db_id)
    if args.action == "resume":
        updated = database.request_paper_cycle_resume(db_id)
        status = "RESUME_REQUESTED"
        message = "Cycle tracking will resume on the next paper processing run without immediate close."
    elif args.action == "abandon":
        updated = database.abandon_paper_cycle(
            db_id,
            args.reason,
            datetime.utcnow().isoformat(),
        )
        status = "ABANDONED"
        message = "Cycle marked as abandoned and excluded from normal OPEN-cycle handling."
    else:
        raise ValueError(f"Unsupported recovery action: {args.action}")

    if not updated:
        raise ValueError(f"OPEN paper cycle not found for db_id={db_id}.")

    print("=== Paper Recovery Action ===")
    print(f"db_id: {db_id}")
    print(f"action: {args.action}")
    print(f"status: {status}")
    print(f"reason: {args.reason}")
    print(message)
    print("Manual close remains available via: python manage.py paper-close-cycle --db-id <id> --reason manual")


def _resolve_paper_recovery_db_id(database, db_id: int | None) -> int:
    if db_id is not None:
        return int(db_id)
    load_with_recovery = getattr(database, "load_open_paper_cycles_with_recovery", None)
    rows = load_with_recovery(limit=1000) if callable(load_with_recovery) else []
    candidates = [
        row for row in rows
        if str(row[16] or "ACTIVE") in {"RECOVERY_REQUIRED", "RESUME_REQUESTED"}
    ]
    if len(candidates) == 1:
        return int(candidates[0][0])
    if not candidates:
        raise ValueError("No unresolved recovery paper cycle found. Pass --db-id explicitly.")
    raise ValueError("Multiple recovery paper cycles found. Pass --db-id explicitly.")


def command_paper_close_watch(args) -> None:
    config, _logger, database = build_context()
    interval = int(args.interval)
    max_checks = int(args.max_checks)
    if interval <= 0:
        raise ValueError("--interval must be greater than 0.")
    if max_checks <= 0:
        raise ValueError("--max-checks must be greater than 0.")

    print("=== Paper Close Watch ===")
    print(f"Profile: {args.profile}")
    print(f"Interval seconds: {interval}")
    print(f"Max checks: {max_checks}")
    print(f"Require Binance: {'yes' if args.require_binance else 'no'}")
    print("Read-only diagnostics. This command does not close paper cycles.")
    print("")

    for check_index in range(1, max_checks + 1):
        print(f"--- Check {check_index}/{max_checks} ---")
        if args.require_binance:
            try:
                current_price, source, timestamp = _load_binance_paper_price(config)
            except Exception as exc:
                print(f"Timestamp: {datetime.now().isoformat()}")
                print("WARNING: Binance price fetch failed.")
                print(f"Error: {exc}")
                print("Skipping close-condition evaluation because --require-binance is enabled.")
                print("")
                if check_index < max_checks:
                    time.sleep(interval)
                continue
        else:
            current_price, source, timestamp = _load_current_paper_price(config, database)

        age_seconds = _price_age_seconds(timestamp)
        stale = _is_stale_price_source(source, age_seconds)
        report = PaperOpenCycleDiagnosticsEngine(database, config).build_report(
            current_price=current_price,
            current_price_source=source,
            current_price_timestamp=timestamp,
            limit=1000,
        )
        open_cycles = [item for item in report.open_cycles if item.profile == args.profile]
        nearest = min(open_cycles, key=lambda item: abs(item.distance_to_target_percent)) if open_cycles else None
        close_ready = [item for item in open_cycles if item.close_condition_met]

        print(f"Price timestamp: {timestamp}")
        print(f"Current price: {current_price:.8f}")
        print(f"Data source: {source}")
        print(f"Stale: {'yes' if stale else 'no'}")
        print(f"Age seconds: {age_seconds:.0f}" if age_seconds is not None else "Age seconds: N/A")
        print(f"Open cycles count: {len(open_cycles)}")
        if nearest is None:
            print("Nearest cycle to target: N/A")
            print("Distance to target: N/A")
            print("Unrealized PnL: N/A")
            print("Close condition met: no")
        else:
            print(
                "Nearest cycle to target: "
                f"db_id={nearest.db_id} cycle_id={nearest.cycle_id} "
                f"direction={nearest.direction} opened_at={nearest.opened_at}"
            )
            print(
                "Distance to target: "
                f"{nearest.distance_to_target:.8f} "
                f"({nearest.distance_to_target_percent:.5f}%)"
            )
            print(f"Unrealized PnL: {nearest.unrealized_pnl:.8f}")
            print(f"Close condition met: {'yes' if nearest.close_condition_met else 'no'}")
            print(f"Reason: {nearest.reason_not_closed}")

        if close_ready:
            print("")
            print("*** CLOSE CONDITION DETECTED ***")
            for item in close_ready:
                print(
                    f"db_id={item.db_id} cycle_id={item.cycle_id} "
                    f"direction={item.direction} target={item.target_price:.8f} "
                    f"current={item.current_price:.8f} unrealized_pnl={item.unrealized_pnl:.8f}"
                )
            print("This watch command did not close anything.")
            print("Run long-paper-run or paper close execution to process eligible cycles.")
            if args.stop_on_close_condition:
                print("Stopping because --stop-on-close-condition was set.")
                break
        print("")

        if check_index < max_checks:
            time.sleep(interval)


def command_paper_stats(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_cycles(limit=args.limit)
    stats = PaperAnalyticsEngine().build_from_rows(rows)

    PaperTradingCliRenderer().render_paper_stats(stats, title="PAPER STATS")


def command_paper_safety(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_safety_events(limit=args.limit)

    print("=== Paper Safety Events ===")
    if not rows:
        print("Paper safety events С‰Рµ РЅРµРјР°С”.")
        return

    for timestamp, level, allowed, reason, value in rows:
        status = "ALLOWED" if allowed else "BLOCKED"
        print(f"{timestamp} | {level} | {status} | value={value:.8f} | {reason}")


def command_paper_report(args) -> None:
    _config, _logger, database = build_context()

    cycle_rows = database.load_recent_paper_cycles(limit=args.limit)
    safety_rows = database.load_recent_paper_safety_events(limit=args.limit)
    stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)

    exporter = PaperReportExporter()
    cycles_path = exporter.export_cycles_csv(cycle_rows)
    safety_path = exporter.export_safety_csv(safety_rows)
    summary_path = exporter.export_summary_csv(stats)

    print("=== Paper Report ===")
    print(f"Cycles CSV: {cycles_path}")
    print(f"Safety CSV: {safety_path}")
    print(f"Summary CSV: {summary_path}")
    PaperTradingCliRenderer().render_paper_stats(stats, title="PAPER REPORT SUMMARY")


def command_paper_recovery(args) -> None:
    _config, _logger, database = build_context()
    snapshot = PaperRecoveryManager(database).recover()

    print("=== Paper Recovery Snapshot ===")
    print(f"Portfolio USDT: {snapshot.portfolio.usdt:.8f}")
    print(f"Portfolio USDC: {snapshot.portfolio.usdc:.8f}")
    print(f"Portfolio value: {snapshot.portfolio.total_value:.8f}")
    print(f"Active cycles: {snapshot.active_cycles}")
    print(f"Last cycle status: {snapshot.last_cycle_status}")
    print(f"Last cycle net profit: {snapshot.last_cycle_net_profit:.8f}")


def command_paper_states(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_state_transitions(limit=args.limit)

    print("=== Paper State Transitions ===")
    if not rows:
        print("Paper state transitions С‰Рµ РЅРµРјР°С”.")
        return

    for timestamp, previous_state, new_state, reason in rows:
        print(f"{timestamp} | {previous_state} -> {new_state} | {reason}")



def command_paper_runs(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_runs(limit=args.limit)

    print("=== Recent Paper Runs ===")
    if not rows:
        print("Paper runs С‰Рµ РЅРµРјР°С”.")
        return

    for row in rows:
        run_id, timestamp, iterations, opened, closed, stops, usdt, usdc, value, rating, summary = row
        print(
            f"#{run_id} | {timestamp} | iter={iterations} opened={opened} closed={closed} "
            f"stops={stops} value={value:.8f} rating={rating} | {summary}"
        )



def command_gui(args) -> None:
    from gui.app import main as gui_main
    gui_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USDT/USDC Bot MVP management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Р—Р°РїСѓСЃС‚РёС‚Рё BotRunner")
    run_parser.add_argument("--iterations", type=int, default=None, help="РљС–Р»СЊРєС–СЃС‚СЊ С–С‚РµСЂР°С†С–Р№")
    run_parser.add_argument("--interval", type=int, default=None, help="Р†РЅС‚РµСЂРІР°Р» РјС–Р¶ С–С‚РµСЂР°С†С–СЏРјРё РІ СЃРµРєСѓРЅРґР°С…")
    run_parser.set_defaults(func=command_run)

    health_parser = subparsers.add_parser("health", help="РџРµСЂРµРІС–СЂРёС‚Рё РіРѕС‚РѕРІРЅС–СЃС‚СЊ СЃРёСЃС‚РµРјРё")
    health_parser.set_defaults(func=command_health)

    data_source_parser = subparsers.add_parser(
        "data-source-check",
        help="Check the configured market-data source",
    )
    data_source_parser.set_defaults(func=command_data_source_check)

    migrate_parser = subparsers.add_parser("migrate", help="Р—Р°РїСѓСЃС‚РёС‚Рё SQLite РјС–РіСЂР°С†С–С—")
    migrate_parser.set_defaults(func=command_migrate)

    stats_parser = subparsers.add_parser("stats", help="РџРѕРєР°Р·Р°С‚Рё СЃС‚Р°С‚РёСЃС‚РёРєСѓ")
    stats_parser.set_defaults(func=command_stats)

    strategy_report_parser = subparsers.add_parser("strategy-report", help="Show strategy validation summary")
    strategy_report_parser.set_defaults(func=command_strategy_report)

    strategy_tuning_parser = subparsers.add_parser(
        "strategy-tuning-report",
        help="Simulate softer confidence thresholds using saved signals",
    )
    strategy_tuning_parser.add_argument("--top", type=int, default=5)
    strategy_tuning_parser.set_defaults(func=command_strategy_tuning_report)

    decision_diagnostics_parser = subparsers.add_parser(
        "decision-diagnostics",
        help="Show decision reason diagnostics",
    )
    decision_diagnostics_parser.add_argument("--top", type=int, default=5)
    decision_diagnostics_parser.set_defaults(func=command_decision_diagnostics)

    risk_diagnostics_parser = subparsers.add_parser(
        "risk-diagnostics",
        help="Show risk validation diagnostics",
    )
    risk_diagnostics_parser.add_argument("--top", type=int, default=5)
    risk_diagnostics_parser.add_argument("--latest", type=int, default=5)
    risk_diagnostics_parser.set_defaults(func=command_risk_diagnostics)

    risk_profitability_parser = subparsers.add_parser(
        "risk-profitability-diagnostics",
        help="Show profitability breakdown for blocked BUY/SELL risk decisions",
    )
    risk_profitability_parser.add_argument("--limit", type=int, default=10)
    risk_profitability_parser.set_defaults(func=command_risk_profitability_diagnostics)

    fee_model_parser = subparsers.add_parser(
        "fee-model-report",
        help="Audit configured fee model usage across backtest, paper, and risk checks",
    )
    fee_model_parser.add_argument("--trade-size", type=float, default=10.0)
    fee_model_parser.set_defaults(func=command_fee_model_report)

    confidence_diagnostics_parser = subparsers.add_parser(
        "confidence-diagnostics",
        help="Show confidence score diagnostics",
    )
    confidence_diagnostics_parser.add_argument("--top", type=int, default=5)
    confidence_diagnostics_parser.set_defaults(func=command_confidence_diagnostics)

    entry_zone_diagnostics_parser = subparsers.add_parser(
        "entry-zone-diagnostics",
        help="Show saved market snapshot entry zone diagnostics",
    )
    entry_zone_diagnostics_parser.set_defaults(func=command_entry_zone_diagnostics)

    filter_pass_diagnostics_parser = subparsers.add_parser(
        "filter-pass-diagnostics",
        help="Show filter pass/fail diagnostics for entry-zone snapshots",
    )
    filter_pass_diagnostics_parser.add_argument("--latest", type=int, default=5)
    filter_pass_diagnostics_parser.set_defaults(func=command_filter_pass_diagnostics)

    order_book_diagnostics_parser = subparsers.add_parser(
        "order-book-diagnostics",
        help="Show order book pressure diagnostics for entry-zone snapshots",
    )
    order_book_diagnostics_parser.add_argument("--latest", type=int, default=10)
    order_book_diagnostics_parser.set_defaults(func=command_order_book_diagnostics)

    order_book_rule_sim_parser = subparsers.add_parser(
        "order-book-rule-sim",
        help="Simulate softer order book confirmation rules using saved snapshots",
    )
    order_book_rule_sim_parser.set_defaults(func=command_order_book_rule_sim)

    center_confidence_diagnostics_parser = subparsers.add_parser(
        "center-confidence-diagnostics",
        help="Show center confidence diagnostics using saved market snapshots",
    )
    center_confidence_diagnostics_parser.add_argument("--latest", type=int, default=10)
    center_confidence_diagnostics_parser.set_defaults(func=command_center_confidence_diagnostics)

    center_confidence_rule_sim_parser = subparsers.add_parser(
        "center-confidence-rule-sim",
        help="Simulate softer center confidence rules using saved snapshots",
    )
    center_confidence_rule_sim_parser.add_argument("--latest", type=int, default=5)
    center_confidence_rule_sim_parser.set_defaults(func=command_center_confidence_rule_sim)

    combined_entry_rule_sim_parser = subparsers.add_parser(
        "combined-entry-rule-sim",
        help="Simulate combined entry rule profiles using saved snapshots",
    )
    combined_entry_rule_sim_parser.add_argument("--latest", type=int, default=5)
    combined_entry_rule_sim_parser.set_defaults(func=command_combined_entry_rule_sim)

    strategy_profile_sim_parser = subparsers.add_parser(
        "strategy-profile-sim",
        help="Simulate experimental strategy profiles using saved snapshots",
    )
    strategy_profile_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_STRATEGY_PROFILES,
        default="strict_current",
    )
    strategy_profile_sim_parser.add_argument("--latest", type=int, default=10)
    strategy_profile_sim_parser.set_defaults(func=command_strategy_profile_sim)

    entry_threshold_parser = subparsers.add_parser(
        "entry-threshold-sensitivity",
        help="Dry-run mean_reversion_v1 entry threshold sensitivity diagnostics",
    )
    entry_threshold_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1",),
        default="mean_reversion_v1",
    )
    entry_threshold_parser.set_defaults(func=command_entry_threshold_sensitivity)

    micro_trend_parser = subparsers.add_parser(
        "micro-trend-sensitivity",
        help="Dry-run mean_reversion_v1 micro trend sensitivity diagnostics",
    )
    micro_trend_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1",),
        default="mean_reversion_v1",
    )
    micro_trend_parser.set_defaults(func=command_micro_trend_sensitivity)

    validation_summary_parser = subparsers.add_parser(
        "validation-summary",
        help="Show aggregate validation status",
    )
    validation_summary_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="strict_current",
    )
    validation_summary_parser.set_defaults(func=command_validation_summary)

    profile_performance_summary_parser = subparsers.add_parser(
        "profile-performance-summary",
        help="Show profile paper-cycle performance with manual-close accounting",
    )
    profile_performance_summary_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    profile_performance_summary_parser.set_defaults(func=command_profile_performance_summary)

    paper_profit_concentration_parser = subparsers.add_parser(
        "paper-profit-concentration",
        help="Show profit concentration diagnostics for paper profile cycles",
    )
    paper_profit_concentration_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    paper_profit_concentration_parser.add_argument(
        "--since-id",
        type=int,
        default=0,
        help="Only include paper cycles with database id greater than this value",
    )
    paper_profit_concentration_parser.set_defaults(func=command_paper_profit_concentration)

    paper_outlier_validation_parser = subparsers.add_parser(
        "paper-outlier-validation",
        help="Show outlier-resistant validation diagnostics for paper profile cycles",
    )
    paper_outlier_validation_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    paper_outlier_validation_parser.add_argument(
        "--since-id",
        type=int,
        default=0,
        help="Only include paper cycles with database id greater than this value",
    )
    paper_outlier_validation_parser.set_defaults(func=command_paper_outlier_validation)

    hf_losing_cycle_diagnostics_parser = subparsers.add_parser(
        "hf-losing-cycle-diagnostics",
        help="Show diagnostics for losing HF paper profile cycles",
    )
    hf_losing_cycle_diagnostics_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_losing_cycle_diagnostics_parser.add_argument(
        "--since-id",
        type=int,
        default=0,
        help="Only include paper cycles with database id greater than this value",
    )
    hf_losing_cycle_diagnostics_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum losing cycles to include in detail output",
    )
    hf_losing_cycle_diagnostics_parser.set_defaults(func=command_hf_losing_cycle_diagnostics)

    hf_profit_audit_parser = subparsers.add_parser(
        "hf-profit-audit",
        help="Audit HF profile profit scope and suspicious paper cycle PnL",
    )
    hf_profit_audit_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_profit_audit_parser.add_argument(
        "--since-id",
        type=int,
        default=None,
        help="Show current-run net for paper cycles with database id greater than this value",
    )
    hf_profit_audit_parser.set_defaults(func=command_hf_profit_audit)

    hf_extreme_move_diagnostics_parser = subparsers.add_parser(
        "hf-extreme-move-diagnostics",
        help="Show HF extreme close price and outlier move diagnostics",
    )
    hf_extreme_move_diagnostics_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_extreme_move_diagnostics_parser.set_defaults(func=command_hf_extreme_move_diagnostics)

    hf_run_regime_comparison_parser = subparsers.add_parser(
        "hf-run-regime-comparison",
        help="Compare two HF paper-cycle runs by market regime diagnostics",
    )
    hf_run_regime_comparison_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_run_regime_comparison_parser.add_argument("--good-since-id", type=int, default=None)
    hf_run_regime_comparison_parser.add_argument("--bad-since-id", type=int, default=None)
    hf_run_regime_comparison_parser.add_argument("--run-a-since-id", type=int, default=None)
    hf_run_regime_comparison_parser.add_argument("--run-b-since-id", type=int, default=None)
    hf_run_regime_comparison_parser.add_argument("--limit", type=int, default=None)
    hf_run_regime_comparison_parser.set_defaults(func=command_hf_run_regime_comparison)

    hf_velocity_filter_sim_parser = subparsers.add_parser(
        "hf-velocity-filter-sim",
        help="Dry-run HF v1 velocity/drift entry filter scenarios",
    )
    hf_velocity_filter_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_velocity_filter_sim_parser.add_argument("--since-id", type=int, default=0)
    hf_velocity_filter_sim_parser.add_argument("--velocity-threshold", type=_positive_decimal_float, default=None)
    hf_velocity_filter_sim_parser.add_argument("--drift-threshold", type=_positive_decimal_float, default=None)
    hf_velocity_filter_sim_parser.add_argument("--require-direction-confirmed", action="store_true")
    hf_velocity_filter_sim_parser.add_argument("--limit", type=int, default=None)
    hf_velocity_filter_sim_parser.set_defaults(func=command_hf_velocity_filter_sim)

    hf_regime_filter_sim_parser = subparsers.add_parser(
        "hf-regime-filter-sim",
        help="Dry-run regime-aware HF velocity filter scenarios",
    )
    hf_regime_filter_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_regime_filter_sim_parser.add_argument("--since-id", type=int, default=0)
    hf_regime_filter_sim_parser.add_argument("--limit", type=int, default=None)
    hf_regime_filter_sim_parser.add_argument(
        "--velocity-threshold",
        type=_positive_decimal_float,
        default=0.00002,
    )
    hf_regime_filter_sim_parser.set_defaults(func=command_hf_regime_filter_sim)

    hf_production_readiness_parser = subparsers.add_parser(
        "hf-production-readiness",
        help="Diagnostics-only readiness audit for the frozen HF v1 baseline",
    )
    hf_production_readiness_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_production_readiness_parser.set_defaults(func=command_hf_production_readiness)

    hf_real_dry_run_parser = subparsers.add_parser(
        "hf-real-dry-run",
        help="Diagnostics-only real exchange dry-run for the frozen HF v1 baseline",
    )
    hf_real_dry_run_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_real_dry_run_parser.add_argument(
        "--pilot-stake",
        type=_positive_decimal_float,
        default=None,
        help="Manual proposed pilot stake for dry-run sizing only. Does not create orders.",
    )
    hf_real_dry_run_parser.set_defaults(func=command_hf_real_dry_run)

    hf_small_real_pilot_parser = subparsers.add_parser(
        "hf-small-real-pilot",
        help="Explicitly confirmed small real SPOT pilot for frozen HF v1 only",
    )
    hf_small_real_pilot_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_small_real_pilot_parser.add_argument("--pilot-stake", type=_positive_decimal_float, required=True)
    hf_small_real_pilot_parser.add_argument("--confirm-real-pilot", action="store_true")
    hf_small_real_pilot_parser.add_argument(
        "--max-cycles-per-run",
        type=_positive_int,
        default=1,
        help="Hard cap for this pilot run; values above 1 are refused by safety gates.",
    )
    hf_small_real_pilot_parser.set_defaults(func=command_hf_small_real_pilot)

    hf_small_real_pilot_watch_parser = subparsers.add_parser(
        "hf-small-real-pilot-watch",
        help="Watch live HF v1 signal and place at most one confirmed small real pilot order",
    )
    hf_small_real_pilot_watch_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_small_real_pilot_watch_parser.add_argument("--pilot-stake", type=_positive_decimal_float, required=True)
    hf_small_real_pilot_watch_parser.add_argument("--confirm-real-pilot", action="store_true")
    hf_small_real_pilot_watch_parser.add_argument("--max-iterations", type=_positive_int, default=300)
    hf_small_real_pilot_watch_parser.add_argument("--interval", type=_decimal_float, default=1.0)
    hf_small_real_pilot_watch_parser.set_defaults(func=command_hf_small_real_pilot_watch)

    hf_real_pilot_status_parser = subparsers.add_parser(
        "hf-real-pilot-status",
        help="Show isolated HF v1 real pilot status and safety state",
    )
    hf_real_pilot_status_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_real_pilot_status_parser.set_defaults(func=command_hf_real_pilot_status)

    hf_real_pilot_close_watch_parser = subparsers.add_parser(
        "hf-real-pilot-close-watch",
        help="Watch an existing HF v1 real pilot cycle and place at most one confirmed close order",
    )
    hf_real_pilot_close_watch_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    hf_real_pilot_close_watch_parser.add_argument("--confirm-real-pilot", action="store_true")
    hf_real_pilot_close_watch_parser.add_argument("--max-iterations", type=_positive_int, default=300)
    hf_real_pilot_close_watch_parser.add_argument("--interval", type=_decimal_float, default=1.0)
    hf_real_pilot_close_watch_parser.set_defaults(func=command_hf_real_pilot_close_watch)

    extreme_market_discovery_parser = subparsers.add_parser(
        "extreme-market-discovery",
        help="Discover and summarize extreme market events from HF data",
    )
    extreme_market_discovery_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    extreme_market_discovery_parser.set_defaults(func=command_extreme_market_discovery)

    extreme_replay_parser = subparsers.add_parser(
        "extreme-replay",
        help="Replay discovered extreme events without trading",
    )
    extreme_replay_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    extreme_replay_parser.add_argument("--output", default="reports/extreme_replay_report.txt")
    extreme_replay_parser.set_defaults(func=command_extreme_replay)

    extreme_replay_ranking_parser = subparsers.add_parser(
        "extreme-replay-ranking",
        help="Rank Extreme Replay scenarios by stability and risk",
    )
    extreme_replay_ranking_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    extreme_replay_ranking_parser.add_argument("--output", default="reports/extreme_replay_ranking.txt")
    extreme_replay_ranking_parser.set_defaults(func=command_extreme_replay_ranking)

    extreme_signal_discovery_parser = subparsers.add_parser(
        "extreme-signal-discovery",
        help="Discover visible pre-event signals before extreme events",
    )
    extreme_signal_discovery_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    extreme_signal_discovery_parser.add_argument("--output", default="reports/extreme_signal_discovery_report.txt")
    extreme_signal_discovery_parser.set_defaults(func=command_extreme_signal_discovery)

    extreme_signal_leadtime_parser = subparsers.add_parser(
        "extreme-signal-leadtime",
        help="Analyze when Extreme pre-event signals become visible",
    )
    extreme_signal_leadtime_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_hf_micro_v1",
    )
    extreme_signal_leadtime_parser.add_argument("--output", default="reports/extreme_signal_leadtime_report.txt")
    extreme_signal_leadtime_parser.set_defaults(func=command_extreme_signal_leadtime)

    extreme_paper_signal_parser = subparsers.add_parser(
        "extreme-paper-signal-diagnostics",
        help="Analyze false positive signals for Extreme paper profile",
    )
    extreme_paper_signal_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="extreme_strategy_v1",
    )
    extreme_paper_signal_parser.add_argument("--limit", type=int, default=None)
    extreme_paper_signal_parser.set_defaults(func=command_extreme_paper_signal_diagnostics)

    extreme_late_entry_parser = subparsers.add_parser(
        "extreme-late-entry-diagnostics",
        help="Analyze late-entry and extreme-price losses for Extreme paper profile",
    )
    extreme_late_entry_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="extreme_strategy_v1",
    )
    extreme_late_entry_parser.set_defaults(func=command_extreme_late_entry_diagnostics)

    notifications_parser = subparsers.add_parser("notifications", help="РџРѕРєР°Р·Р°С‚Рё РїРѕРІС–РґРѕРјР»РµРЅРЅСЏ")
    notifications_parser.add_argument("--limit", type=int, default=10)
    notifications_parser.add_argument("--mark-read", action="store_true")
    notifications_parser.set_defaults(func=command_notifications)

    audit_parser = subparsers.add_parser("audit", help="РџРѕРєР°Р·Р°С‚Рё РѕСЃС‚Р°РЅРЅС– audit-Р·Р°РїРёСЃРё")
    audit_parser.add_argument("--limit", type=int, default=10)
    audit_parser.set_defaults(func=command_audit)

    backtest_parser = subparsers.add_parser("backtest", help="Р—Р°РїСѓСЃС‚РёС‚Рё С–СЃС‚РѕСЂРёС‡РЅРёР№ backtest")
    backtest_parser.add_argument("--interval", type=str, default=None)
    backtest_parser.add_argument("--limit", type=int, default=None)
    backtest_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="strict_current",
    )
    backtest_parser.add_argument("--debug-decisions", action="store_true")
    backtest_parser.set_defaults(func=command_backtest)

    backtest_runs_parser = subparsers.add_parser("backtest-runs", help="РџРѕРєР°Р·Р°С‚Рё РѕСЃС‚Р°РЅРЅС– backtest-Р·Р°РїСѓСЃРєРё")
    backtest_runs_parser.add_argument("--limit", type=int, default=10)
    backtest_runs_parser.set_defaults(func=command_backtest_runs)

    backtest_periods_parser = subparsers.add_parser("backtest-periods", help="РџРѕРєР°Р·Р°С‚Рё period analytics РґР»СЏ backtest run")
    backtest_periods_parser.add_argument("run_id", type=int)
    backtest_periods_parser.set_defaults(func=command_backtest_periods)

    backtest_compare_parser = subparsers.add_parser("backtest-compare", help="РџРѕСЂС–РІРЅСЏС‚Рё backtest-Р·Р°РїСѓСЃРєРё")
    backtest_compare_parser.add_argument("--limit", type=int, default=20)
    backtest_compare_parser.add_argument("--export", action="store_true")
    backtest_compare_parser.set_defaults(func=command_backtest_compare)

    sweep_parser = subparsers.add_parser("parameter-sweep", help="РџС–РґС–Р±СЂР°С‚Рё РїР°СЂР°РјРµС‚СЂРё С‡РµСЂРµР· СЃРµСЂС–СЋ backtest")
    sweep_parser.add_argument("--interval", type=str, default=None)
    sweep_parser.add_argument("--limit", type=int, default=None)
    sweep_parser.add_argument("--target-profits", type=str, default="0.0001,0.0002,0.0003")
    sweep_parser.add_argument("--trade-sizes", type=str, default="0.05,0.10,0.15")
    sweep_parser.add_argument("--top", type=int, default=10)
    sweep_parser.add_argument("--export", action="store_true")
    sweep_parser.set_defaults(func=command_parameter_sweep)

    walk_parser = subparsers.add_parser("walk-forward", help="Walk-forward РїРµСЂРµРІС–СЂРєР° РїР°СЂР°РјРµС‚СЂС–РІ")
    walk_parser.add_argument("--interval", type=str, default=None)
    walk_parser.add_argument("--limit", type=int, default=None)
    walk_parser.add_argument("--target-profits", type=str, default="0.0001,0.0002,0.0003")
    walk_parser.add_argument("--trade-sizes", type=str, default="0.05,0.10,0.15")
    walk_parser.add_argument("--train-size", type=int, default=300)
    walk_parser.add_argument("--test-size", type=int, default=100)
    walk_parser.add_argument("--export", action="store_true")
    walk_parser.set_defaults(func=command_walk_forward)

    walk_runs_parser = subparsers.add_parser("walk-forward-runs", help="РџРѕРєР°Р·Р°С‚Рё РѕСЃС‚Р°РЅРЅС– walk-forward Р·Р°РїСѓСЃРєРё")
    walk_runs_parser.add_argument("--limit", type=int, default=10)
    walk_runs_parser.set_defaults(func=command_walk_forward_runs)

    paper_sim_parser = subparsers.add_parser("paper-sim", help="Р—Р°РїСѓСЃС‚РёС‚Рё РєРѕСЂРѕС‚РєСѓ paper trading СЃРёРјСѓР»СЏС†С–СЋ")
    paper_sim_parser.add_argument("--iterations", type=int, default=5)
    paper_sim_parser.set_defaults(func=command_paper_sim)

    paper_orders_parser = subparsers.add_parser("paper-orders", help="РџРѕРєР°Р·Р°С‚Рё РѕСЃС‚Р°РЅРЅС– paper orders")
    paper_orders_parser.add_argument("--limit", type=int, default=20)
    paper_orders_parser.set_defaults(func=command_paper_orders)

    paper_cycle_sim_parser = subparsers.add_parser("paper-cycle-sim", help="Р—Р°РїСѓСЃС‚РёС‚Рё paper cycle СЃРёРјСѓР»СЏС†С–СЋ")
    paper_cycle_sim_parser.add_argument("--iterations", type=int, default=10)
    paper_cycle_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="strict_current",
    )
    paper_cycle_sim_parser.add_argument("--debug-decisions", action="store_true")
    paper_cycle_sim_parser.add_argument("--debug-risk-details", action="store_true")
    paper_cycle_sim_parser.add_argument("--debug-entry-zones", action="store_true")
    paper_cycle_sim_parser.add_argument("--debug-close", action="store_true")
    paper_cycle_sim_parser.add_argument("--force-refresh-market-data", action="store_true")
    paper_cycle_sim_parser.add_argument("--safe-stop", action="store_true")
    paper_cycle_sim_parser.add_argument("--resume-recovery", action="store_true")
    paper_cycle_sim_parser.set_defaults(func=command_paper_cycle_sim)

    collect_closed_cycles_parser = subparsers.add_parser(
        "collect-closed-cycles",
        help="Run paper processing until the selected profile accumulates target CLOSED cycles",
    )
    collect_closed_cycles_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    collect_closed_cycles_parser.add_argument("--target", type=int, default=None)
    collect_closed_cycles_parser.add_argument("--target-new", type=int, default=None)
    collect_closed_cycles_parser.add_argument("--interval", type=int, default=1)
    collect_closed_cycles_parser.add_argument("--max-iterations", type=int, default=None)
    collect_closed_cycles_parser.add_argument("--beep", action=argparse.BooleanOptionalAction, default=True)
    collect_closed_cycles_parser.add_argument("--require-binance", action="store_true")
    collect_closed_cycles_parser.add_argument("--print-every", type=int, default=1)
    collect_closed_cycles_parser.add_argument(
        "--progress-interval",
        type=float,
        default=60.0,
        help="Minimum seconds between regular compact progress updates. Important events are printed immediately.",
    )
    collect_closed_cycles_parser.add_argument("--safe-stop", action="store_true")
    collect_closed_cycles_parser.add_argument("--resume-recovery", action="store_true")
    collect_closed_cycles_parser.add_argument("--compact", action="store_true")
    collect_closed_cycles_parser.add_argument("--verbose-rich", action="store_true")
    collect_closed_cycles_parser.add_argument("--events-only", action="store_true")
    collect_closed_cycles_parser.set_defaults(func=command_collect_closed_cycles)

    long_paper_run_parser = subparsers.add_parser("long-paper-run", help="Run long paper validation workflow")
    long_paper_run_parser.add_argument("--iterations", type=int, default=500)
    long_paper_run_parser.add_argument("--interval", type=int, default=5)
    long_paper_run_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="strict_current",
    )
    long_paper_run_parser.add_argument("--debug-close", action="store_true")
    long_paper_run_parser.set_defaults(func=command_long_paper_run)

    long_paper_runs_parser = subparsers.add_parser("long-paper-runs", help="Show recent long paper runs")
    long_paper_runs_parser.add_argument("--limit", type=int, default=20)
    long_paper_runs_parser.set_defaults(func=command_long_paper_runs)

    paper_cycles_parser = subparsers.add_parser("paper-cycles", help="РџРѕРєР°Р·Р°С‚Рё РѕСЃС‚Р°РЅРЅС– paper cycles")
    paper_cycles_parser.add_argument("--limit", type=int, default=20)
    paper_cycles_parser.set_defaults(func=command_paper_cycles)

    paper_open_cycles_parser = subparsers.add_parser("paper-open-cycles", help="Show diagnostics for open paper cycles")
    paper_open_cycles_parser.add_argument("--limit", type=int, default=100)
    paper_open_cycles_parser.set_defaults(func=command_paper_open_cycles)

    paper_close_cycle_parser = subparsers.add_parser(
        "paper-close-cycle",
        help="Manually close an OPEN paper cycle at current Binance price",
    )
    paper_close_cycle_parser.add_argument("--db-id", type=int, required=True)
    paper_close_cycle_parser.add_argument(
        "--reason",
        choices=("manual", "timeout", "stale", "test_cleanup"),
        default="manual",
    )
    paper_close_cycle_parser.set_defaults(func=command_paper_close_cycle)

    paper_recovery_action_parser = subparsers.add_parser(
        "paper-recovery-action",
        help="Resolve an OPEN paper cycle that requires operator recovery",
    )
    paper_recovery_action_parser.add_argument("--db-id", type=int, default=None)
    paper_recovery_action_parser.add_argument(
        "--action",
        choices=("resume", "abandon"),
        required=True,
    )
    paper_recovery_action_parser.add_argument("--reason", default="operator_recovery")
    paper_recovery_action_parser.set_defaults(func=command_paper_recovery_action)

    paper_close_watch_parser = subparsers.add_parser(
        "paper-close-watch",
        help="Watch open paper cycles and report close-condition readiness",
    )
    paper_close_watch_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    paper_close_watch_parser.add_argument("--interval", type=int, default=60)
    paper_close_watch_parser.add_argument("--max-checks", type=int, default=480)
    paper_close_watch_parser.add_argument("--require-binance", action="store_true")
    paper_close_watch_parser.add_argument("--stop-on-close-condition", action="store_true")
    paper_close_watch_parser.set_defaults(func=command_paper_close_watch)

    target_profit_sensitivity_parser = subparsers.add_parser(
        "target-profit-sensitivity",
        help="Dry-run target profit sensitivity for open paper cycles",
    )
    target_profit_sensitivity_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1", "mean_reversion_v2"),
        default="mean_reversion_v2",
    )
    target_profit_sensitivity_parser.set_defaults(func=command_target_profit_sensitivity)

    direction_outcome_parser = subparsers.add_parser(
        "direction-outcome-diagnostics",
        help="Diagnose whether paper cycle directions are moving toward targets",
    )
    direction_outcome_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1", "mean_reversion_v2"),
        default="mean_reversion_v2",
    )
    direction_outcome_parser.set_defaults(func=command_direction_outcome_diagnostics)

    trend_alignment_parser = subparsers.add_parser(
        "trend-alignment-diagnostics",
        help="Show 1h trend alignment diagnostics for paper cycles",
    )
    trend_alignment_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    trend_alignment_parser.set_defaults(func=command_trend_alignment_diagnostics)

    trend_filter_sim_parser = subparsers.add_parser(
        "trend-filter-sim",
        help="Dry-run 1h trend filter variants for mean-reversion candidates",
    )
    trend_filter_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    trend_filter_sim_parser.set_defaults(func=command_trend_filter_sim)

    trend_strength_parser = subparsers.add_parser(
        "trend-strength-diagnostics",
        help="Show 1h trend strength and flat-trend threshold diagnostics",
    )
    trend_strength_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    trend_strength_parser.set_defaults(func=command_trend_strength_diagnostics)

    range_shift_parser = subparsers.add_parser(
        "range-shift-diagnostics",
        help="Show paper cycle diagnostics for center/range shifts after entry",
    )
    range_shift_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    range_shift_parser.set_defaults(func=command_range_shift_diagnostics)

    target_rebase_parser = subparsers.add_parser(
        "target-rebase-diagnostics",
        help="Dry-run target rebase options for stalled paper cycles",
    )
    target_rebase_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    target_rebase_parser.set_defaults(func=command_target_rebase_diagnostics)

    break_even_rebase_parser = subparsers.add_parser(
        "break-even-rebase-sim",
        help="Dry-run break-even target rebase variants for stalled paper cycles",
    )
    break_even_rebase_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    break_even_rebase_parser.set_defaults(func=command_break_even_rebase_sim)

    holding_horizon_parser = subparsers.add_parser(
        "holding-horizon-diagnostics",
        help="Estimate how many snapshots are needed to hit paper targets",
    )
    holding_horizon_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1", "mean_reversion_v2"),
        default="mean_reversion_v2",
    )
    holding_horizon_parser.set_defaults(func=command_holding_horizon_diagnostics)

    profile_comparison_parser = subparsers.add_parser(
        "profile-comparison-diagnostics",
        help="Dry-run comparison of mean-reversion profile variants",
    )
    profile_comparison_parser.set_defaults(func=command_profile_comparison_diagnostics)

    post_entry_path_parser = subparsers.add_parser(
        "post-entry-path-diagnostics",
        help="Show price paths after mean-reversion entry candidates",
    )
    post_entry_path_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1", "mean_reversion_v2"),
        default="mean_reversion_v2",
    )
    post_entry_path_parser.set_defaults(func=command_post_entry_path_diagnostics)

    entry_confirmation_parser = subparsers.add_parser(
        "entry-confirmation-diagnostics",
        help="Dry-run confirmation variants before mean-reversion entries",
    )
    entry_confirmation_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1", "mean_reversion_v2"),
        default="mean_reversion_v2",
    )
    entry_confirmation_parser.set_defaults(func=command_entry_confirmation_diagnostics)

    partial_target_parser = subparsers.add_parser(
        "partial-target-diagnostics",
        help="Dry-run lower take-profit and partial target diagnostics",
    )
    partial_target_parser.add_argument(
        "--profile",
        choices=("mean_reversion_v1", "mean_reversion_v2"),
        default="mean_reversion_v2",
    )
    partial_target_parser.set_defaults(func=command_partial_target_diagnostics)

    exit_risk_parser = subparsers.add_parser(
        "exit-risk-diagnostics",
        help="Dry-run stop-loss and max-holding diagnostics for paper cycles",
    )
    exit_risk_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    exit_risk_parser.set_defaults(func=command_exit_risk_diagnostics)

    max_holding_sensitivity_parser = subparsers.add_parser(
        "max-holding-sensitivity",
        help="Dry-run max holding time sensitivity for paper cycles",
    )
    max_holding_sensitivity_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    max_holding_sensitivity_parser.set_defaults(func=command_max_holding_sensitivity)

    exit_rule_sim_parser = subparsers.add_parser(
        "exit-rule-sim",
        help="Dry-run exit rule simulation for paper cycles",
    )
    exit_rule_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    exit_rule_sim_parser.set_defaults(func=command_exit_rule_sim)

    exit_rule_optimizer_parser = subparsers.add_parser(
        "exit-rule-optimizer",
        help="Dry-run optimizer for stale-cycle exit rules",
    )
    exit_rule_optimizer_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    exit_rule_optimizer_parser.set_defaults(func=command_exit_rule_optimizer)

    exit_tolerance_sim_parser = subparsers.add_parser(
        "exit-tolerance-sim",
        help="Dry-run close tolerance simulation for open paper cycles",
    )
    exit_tolerance_sim_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    exit_tolerance_sim_parser.set_defaults(func=command_exit_tolerance_sim)

    high_frequency_parser = subparsers.add_parser(
        "high-frequency-diagnostics",
        help="Research high-frequency micro-cycle potential without changing runtime",
    )
    high_frequency_parser.set_defaults(func=command_high_frequency_diagnostics)

    collect_market_snapshots_parser = subparsers.add_parser(
        "collect-market-snapshots",
        help="Collect live market snapshots for high-frequency research without trading",
    )
    collect_market_snapshots_parser.add_argument("--duration-hours", type=float, default=24.0)
    collect_market_snapshots_parser.add_argument("--interval", type=float, default=5.0)
    collect_market_snapshots_parser.add_argument("--max-snapshots", type=int, default=None)
    collect_market_snapshots_parser.set_defaults(func=command_collect_market_snapshots)

    hf_dataset_summary_parser = subparsers.add_parser(
        "high-frequency-dataset-summary",
        help="Summarize collected high-frequency market snapshots",
    )
    hf_dataset_summary_parser.set_defaults(func=command_high_frequency_dataset_summary)

    micro_cycle_sim_parser = subparsers.add_parser(
        "micro-cycle-sim",
        help="Dry-run high-frequency micro-cycle simulation over collected HF snapshots",
    )
    micro_cycle_sim_parser.add_argument("--scenario", choices=MICRO_CYCLE_SCENARIOS, default=None)
    micro_cycle_sim_parser.add_argument("--target", type=_positive_decimal_float, default=None)
    micro_cycle_sim_parser.add_argument("--max-holding-seconds", type=float, default=None)
    micro_cycle_sim_parser.add_argument("--show-cycles", action="store_true")
    micro_cycle_sim_parser.set_defaults(func=command_micro_cycle_sim)

    micro_cycle_grid_search_parser = subparsers.add_parser(
        "micro-cycle-grid-search",
        help="Run diagnostics-only grid search over HF micro-cycle parameters",
    )
    micro_cycle_grid_search_parser.add_argument("--top", type=int, default=20)
    micro_cycle_grid_search_parser.add_argument("--scenario", choices=MICRO_CYCLE_GRID_SCENARIOS, default=None)
    micro_cycle_grid_search_parser.add_argument("--min-cycles-day", type=float, default=100.0)
    micro_cycle_grid_search_parser.add_argument("--max-drawdown", type=float, default=0.005)
    micro_cycle_grid_search_parser.add_argument("--export-csv", default=None)
    micro_cycle_grid_search_parser.set_defaults(func=command_micro_cycle_grid_search)

    hf_micro_grid_sim_parser = subparsers.add_parser(
        "hf-micro-grid-sim",
        help="Dry-run HF micro-cycle grid simulation with layered capital allocation",
    )
    hf_micro_grid_sim_parser.add_argument(
        "--scenario",
        choices=MICRO_CYCLE_SCENARIOS,
        default=HF_GRID_DEFAULT_SCENARIO,
    )
    hf_micro_grid_sim_parser.add_argument(
        "--target",
        type=_positive_decimal_float,
        default=HF_GRID_DEFAULT_TARGET_PERCENT,
    )
    hf_micro_grid_sim_parser.add_argument(
        "--max-holding-seconds",
        type=_positive_decimal_float,
        default=HF_GRID_DEFAULT_MAX_HOLDING_SECONDS,
    )
    hf_micro_grid_sim_parser.add_argument(
        "--layer-size",
        type=_positive_decimal_float,
        default=HF_GRID_DEFAULT_LAYER_SIZE,
    )
    hf_micro_grid_sim_parser.add_argument(
        "--max-layers",
        type=_positive_int,
        default=HF_GRID_DEFAULT_MAX_LAYERS,
    )
    hf_micro_grid_sim_parser.add_argument(
        "--directional-exposure-guard",
        action="store_true",
        help="Block same-direction layers when that active direction basket is already unrealized-negative",
    )
    hf_micro_grid_sim_parser.add_argument(
        "--guard-min-layers",
        type=_positive_int,
        default=HF_GRID_DEFAULT_GUARD_MIN_LAYERS,
        help="Minimum same-direction active layers before directional exposure guard can block",
    )
    hf_micro_grid_sim_parser.add_argument(
        "--guard-loss-threshold",
        type=_decimal_float,
        default=HF_GRID_DEFAULT_GUARD_LOSS_THRESHOLD,
        help="Same-direction unrealized basket PnL threshold for directional guard blocking",
    )
    hf_micro_grid_sim_parser.add_argument(
        "--show-drawdown-events",
        action="store_true",
        help="Show detailed worst basket drawdown events and aggregate causes",
    )
    hf_micro_grid_sim_parser.add_argument(
        "--drawdown-events-limit",
        type=_positive_int,
        default=5,
        help="Number of worst drawdown events to print when --show-drawdown-events is used",
    )
    hf_micro_grid_sim_parser.set_defaults(func=command_hf_micro_grid_sim)

    hf_micro_grid_guard_sweep_parser = subparsers.add_parser(
        "hf-micro-grid-guard-sweep",
        help="Run diagnostics-only sweep over HF grid directional exposure guard parameters",
    )
    hf_micro_grid_guard_sweep_parser.add_argument("--top", type=_positive_int, default=20)
    hf_micro_grid_guard_sweep_parser.add_argument("--min-cycles-day", type=_positive_decimal_float, default=150.0)
    hf_micro_grid_guard_sweep_parser.add_argument("--max-drawdown", type=_positive_decimal_float, default=0.01)
    hf_micro_grid_guard_sweep_parser.add_argument("--max-average-capital", type=_positive_decimal_float, default=50.0)
    hf_micro_grid_guard_sweep_parser.add_argument("--export-csv", default=None)
    hf_micro_grid_guard_sweep_parser.set_defaults(func=command_hf_micro_grid_guard_sweep)

    target_resolution_parser = subparsers.add_parser(
        "target-resolution-diagnostics",
        help="Diagnose whether micro-cycle target values collapse to equivalent effective targets",
    )
    target_resolution_parser.add_argument("--compare", nargs=2, type=_positive_decimal_float, default=None)
    target_resolution_parser.add_argument("--compare-simulation", nargs=2, type=_positive_decimal_float, default=None)
    target_resolution_parser.add_argument(
        "--scenario",
        choices=MICRO_CYCLE_SCENARIOS,
        default="short_term_mean_reversion",
    )
    target_resolution_parser.add_argument("--max-holding-seconds", type=float, default=270.0)
    target_resolution_parser.set_defaults(func=command_target_resolution_diagnostics)

    market_session_parser = subparsers.add_parser(
        "market-session-diagnostics",
        help="Diagnose paper cycle performance by market session",
    )
    market_session_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    market_session_parser.set_defaults(func=command_market_session_diagnostics)

    session_filter_parser = subparsers.add_parser(
        "session-filter-sim",
        help="Dry-run session filter variants for paper cycles",
    )
    session_filter_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    session_filter_parser.set_defaults(func=command_session_filter_sim)

    build_ml_dataset_parser = subparsers.add_parser(
        "build-ml-dataset",
        help="Export a supervised historical ML dataset for future model research",
    )
    build_ml_dataset_parser.add_argument("--symbol", default="USDCUSDT")
    build_ml_dataset_parser.add_argument("--interval", default="1m")
    build_ml_dataset_parser.add_argument("--limit", type=int, default=5000)
    build_ml_dataset_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    build_ml_dataset_parser.add_argument(
        "--dataset-mode",
        choices=SUPPORTED_DATASET_MODES,
        default="profile",
    )
    build_ml_dataset_parser.set_defaults(func=command_build_ml_dataset)

    ml_dataset_coverage_parser = subparsers.add_parser(
        "ml-dataset-coverage",
        help="Diagnose why a historical ML dataset has few or no candidate rows",
    )
    ml_dataset_coverage_parser.add_argument("--symbol", default="USDCUSDT")
    ml_dataset_coverage_parser.add_argument("--interval", default="1m")
    ml_dataset_coverage_parser.add_argument("--limit", type=int, default=1000)
    ml_dataset_coverage_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="mean_reversion_v2_small_target",
    )
    ml_dataset_coverage_parser.add_argument(
        "--dataset-mode",
        choices=SUPPORTED_DATASET_MODES,
        default="profile",
    )
    ml_dataset_coverage_parser.set_defaults(func=command_ml_dataset_coverage)

    ml_dataset_summary_parser = subparsers.add_parser(
        "ml-dataset-summary",
        help="Summarize target-hit rates in an exported ML dataset CSV",
    )
    ml_dataset_summary_parser.add_argument("--file", required=True)
    ml_dataset_summary_parser.set_defaults(func=command_ml_dataset_summary)

    train_ml_baseline_parser = subparsers.add_parser(
        "train-ml-baseline",
        help="Train an offline baseline ML model and export an analysis report",
    )
    train_ml_baseline_parser.add_argument("--file", required=True)
    train_ml_baseline_parser.set_defaults(func=command_train_ml_baseline)

    paper_stats_parser = subparsers.add_parser("paper-stats", help="РџРѕРєР°Р·Р°С‚Рё paper trading СЃС‚Р°С‚РёСЃС‚РёРєСѓ")
    paper_stats_parser.add_argument("--limit", type=int, default=100)
    paper_stats_parser.set_defaults(func=command_paper_stats)

    paper_safety_parser = subparsers.add_parser("paper-safety", help="РџРѕРєР°Р·Р°С‚Рё paper safety events")
    paper_safety_parser.add_argument("--limit", type=int, default=20)
    paper_safety_parser.set_defaults(func=command_paper_safety)

    paper_report_parser = subparsers.add_parser("paper-report", help="CSV-Р·РІС–С‚ РїРѕ paper trading")
    paper_report_parser.add_argument("--limit", type=int, default=500)
    paper_report_parser.set_defaults(func=command_paper_report)

    paper_recovery_parser = subparsers.add_parser("paper-recovery", help="РџРѕРєР°Р·Р°С‚Рё paper recovery snapshot")
    paper_recovery_parser.set_defaults(func=command_paper_recovery)

    paper_states_parser = subparsers.add_parser("paper-states", help="РџРѕРєР°Р·Р°С‚Рё paper state transitions")
    paper_states_parser.add_argument("--limit", type=int, default=20)
    paper_states_parser.set_defaults(func=command_paper_states)

    paper_runs_parser = subparsers.add_parser("paper-runs", help="РџРѕРєР°Р·Р°С‚Рё С–СЃС‚РѕСЂС–СЋ paper-run Р·Р°РїСѓСЃРєС–РІ")
    paper_runs_parser.add_argument("--limit", type=int, default=20)
    paper_runs_parser.set_defaults(func=command_paper_runs)

    gui_parser = subparsers.add_parser("gui", help="Р—Р°РїСѓСЃС‚РёС‚Рё PySide6 GUI")
    gui_parser.set_defaults(func=command_gui)

    return parser


def main() -> None:
    configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
