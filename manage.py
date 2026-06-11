import argparse

import sys

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
from paper.paper_trading_engine import PaperTradingEngine
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
from analytics.center_confidence_diagnostics_engine import CenterConfidenceDiagnosticsEngine
from analytics.center_confidence_rule_sim_engine import CenterConfidenceRuleSimulationEngine
from analytics.combined_entry_rule_sim_engine import CombinedEntryRuleSimulationEngine
from analytics.confidence_diagnostics_engine import ConfidenceDiagnosticsEngine
from analytics.data_source_check_engine import DataSourceCheckEngine
from analytics.decision_diagnostics_engine import DecisionDiagnosticsEngine
from analytics.direction_outcome_diagnostics_engine import DirectionOutcomeDiagnosticsEngine
from analytics.entry_zone_diagnostics_engine import EntryZoneDiagnosticsEngine
from analytics.entry_zone_debug_report import EntryZoneDebugReportBuilder
from analytics.entry_threshold_sensitivity_engine import EntryThresholdSensitivityEngine
from analytics.fee_model_report_engine import FeeModelReportEngine
from analytics.filter_pass_diagnostics_engine import FilterPassDiagnosticsEngine
from analytics.holding_horizon_diagnostics_engine import HoldingHorizonDiagnosticsEngine
from analytics.micro_trend_sensitivity_engine import MicroTrendSensitivityEngine
from analytics.order_book_diagnostics_engine import OrderBookDiagnosticsEngine
from analytics.order_book_rule_sim_engine import OrderBookRuleSimulationEngine
from analytics.paper_open_cycle_diagnostics_engine import PaperOpenCycleDiagnosticsEngine
from analytics.post_entry_path_diagnostics_engine import PostEntryPathDiagnosticsEngine
from analytics.profile_comparison_diagnostics_engine import ProfileComparisonDiagnosticsEngine
from analytics.risk_diagnostics_engine import RiskDiagnosticsEngine
from analytics.risk_profitability_diagnostics_engine import RiskProfitabilityDiagnosticsEngine
from analytics.statistics_engine import StatisticsEngine
from analytics.strategy_profile_sim_engine import (
    SUPPORTED_STRATEGY_PROFILES,
    StrategyProfileSimulationEngine,
)
from analytics.strategy_tuning_report_engine import StrategyTuningReportEngine
from analytics.strategy_validation_engine import StrategyValidationEngine
from analytics.target_profit_sensitivity_engine import TargetProfitSensitivityEngine
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
    now = __import__("datetime").datetime.now
    try:
        bid_ask = BinanceMarketDataProvider(base_url=config.binance_base_url).get_bid_ask(config.symbol)
        return bid_ask.mid_price, "BINANCE", now().isoformat()
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
        return 1.0, "DEFAULT_1_0", now().isoformat()


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


def command_validation_summary(args) -> None:
    _config, _logger, database = build_context()
    summary = ValidationSummaryEngine(database).build_summary()

    print("=== Validation Summary ===")
    print(f"Overall status: {summary.overall_status}")
    print(f"Strategy signals: {summary.strategy_signals}")
    print(f"Latest backtest trades: {summary.latest_backtest_trades}")
    print(f"Latest backtest net profit: {summary.latest_backtest_net_profit:.8f}")
    print(f"Paper cycles: {summary.paper_cycles}")
    print(f"Paper net profit: {summary.paper_net_profit:.8f}")
    print(f"Risk blocked rate: {summary.risk_blocked_rate * 100:.2f}%")
    print("Warnings:")
    if summary.warnings:
        for item in summary.warnings:
            print(f"- {item}")
    else:
        print("- None")
    print("Next action:")
    print(summary.next_action)


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
    result = PaperTradingEngine(
        config,
        database,
        bot=bot,
        decision_debug_callback=debug_callback,
        risk_debug_callback=risk_debug_callback,
        entry_zone_debug_callback=entry_zone_debug_callback,
        force_refresh_market_data=args.force_refresh_market_data,
        strategy_profile=profile,
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

    print("=== Paper Cycle Sim ===")
    print(f"Strategy profile: {profile}")
    print(f"Iterations: {result.iterations}")
    print(f"Opened cycles: {result.opened_cycles}")
    print(f"Closed cycles: {result.closed_cycles}")
    print(f"Safety stops: {result.safety_stops}")
    print(f"Final USDT: {result.final_portfolio.usdt:.8f}")
    print(f"Final USDC: {result.final_portfolio.usdc:.8f}")
    print(f"Final value: {result.final_portfolio.total_value:.8f}")

    cycle_rows = database.load_recent_paper_cycles(limit=500)
    safety_rows = database.load_recent_paper_safety_events(limit=500)
    stats = PaperAnalyticsEngine().build_from_rows(cycle_rows)
    insights = PaperInsightsEngine().build(stats, safety_rows)
    paper_run_id = database.save_paper_run(result, insights)
    insights_path = PaperInsightsExporter().export_txt(paper_run_id, insights)
    summary_path = PaperReportExporter().export_summary_csv(stats, strategy_profile=profile)

    print("--- Paper Insights ---")
    print(f"Run ID: {paper_run_id}")
    print(f"Rating: {insights.rating}")
    print(f"Summary: {insights.summary}")
    print(f"Summary CSV: {summary_path}")
    print(f"Insights TXT: {insights_path}")
    if args.debug_entry_zones and entry_zone_debug_builder is not None:
        _print_entry_zone_debug_summary(entry_zone_debug_builder)
    if args.debug_decisions and debug_counter["count"] == 0:
        print("[decision-debug] No potential entry points were evaluated.")
    if args.debug_risk_details and risk_debug_counter["count"] == 0:
        print("[risk-debug] No BUY/SELL risk profitability checks were evaluated.")


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
    result = LongPaperRunWorkflow(config, database).run(
        iterations=args.iterations,
        interval_seconds=args.interval,
        strategy_profile=profile,
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
        print(f"  close_condition_met: {close_status}")
        print(f"  reason_not_closed: {item.reason_not_closed}")


def command_paper_stats(args) -> None:
    _config, _logger, database = build_context()
    rows = database.load_recent_paper_cycles(limit=args.limit)
    stats = PaperAnalyticsEngine().build_from_rows(rows)

    print("=== Paper Stats ===")
    print(f"Total cycles: {stats.total_cycles}")
    print(f"Closed cycles: {stats.closed_cycles}")
    print(f"Winning cycles: {stats.winning_cycles}")
    print(f"Losing cycles: {stats.losing_cycles}")
    print(f"Win rate: {stats.win_rate * 100:.2f}%")
    print(f"Gross profit: {stats.gross_profit:.8f}")
    print(f"Net profit: {stats.net_profit:.8f}")
    print(f"Average net profit: {stats.average_net_profit:.8f}")
    print(f"Profit factor: {stats.profit_factor:.4f}")


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
    print(f"Closed cycles: {stats.closed_cycles}")
    print(f"Win rate: {stats.win_rate * 100:.2f}%")
    print(f"Net profit: {stats.net_profit:.8f}")
    print(f"Profit factor: {stats.profit_factor:.4f}")


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
    validation_summary_parser.set_defaults(func=command_validation_summary)

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
    paper_cycle_sim_parser.add_argument("--force-refresh-market-data", action="store_true")
    paper_cycle_sim_parser.set_defaults(func=command_paper_cycle_sim)

    long_paper_run_parser = subparsers.add_parser("long-paper-run", help="Run long paper validation workflow")
    long_paper_run_parser.add_argument("--iterations", type=int, default=500)
    long_paper_run_parser.add_argument("--interval", type=int, default=5)
    long_paper_run_parser.add_argument(
        "--profile",
        choices=SUPPORTED_RUNTIME_STRATEGY_PROFILES,
        default="strict_current",
    )
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
