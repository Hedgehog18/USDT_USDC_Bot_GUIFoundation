import pytest

from manage import build_parser


def test_manage_cli_has_run_command():
    parser = build_parser()
    args = parser.parse_args(["run", "--iterations", "2", "--interval", "1"])

    assert args.command == "run"
    assert args.iterations == 2
    assert args.interval == 1


def test_manage_cli_has_notifications_command():
    parser = build_parser()
    args = parser.parse_args(["notifications", "--limit", "5"])

    assert args.command == "notifications"
    assert args.limit == 5


def test_manage_cli_has_data_source_check_command():
    parser = build_parser()
    args = parser.parse_args(["data-source-check"])

    assert args.command == "data-source-check"


def test_manage_cli_has_audit_command():
    parser = build_parser()
    args = parser.parse_args(["audit", "--limit", "3"])

    assert args.command == "audit"
    assert args.limit == 3


def test_manage_cli_has_backtest_command():
    parser = build_parser()
    args = parser.parse_args(["backtest", "--interval", "1m", "--limit", "100"])

    assert args.command == "backtest"
    assert args.interval == "1m"
    assert args.limit == 100
    assert args.profile == "strict_current"


def test_manage_cli_backtest_accepts_strategy_profile():
    parser = build_parser()
    args = parser.parse_args([
        "backtest",
        "--interval",
        "1m",
        "--limit",
        "100",
        "--profile",
        "mean_reversion_v1",
        "--debug-decisions",
    ])

    assert args.profile == "mean_reversion_v1"
    assert args.debug_decisions is True


def test_manage_cli_backtest_accepts_mean_reversion_v2_profile():
    parser = build_parser()
    args = parser.parse_args([
        "backtest",
        "--interval",
        "1m",
        "--limit",
        "100",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.profile == "mean_reversion_v2"


def test_manage_cli_backtest_accepts_small_target_profile():
    parser = build_parser()
    args = parser.parse_args([
        "backtest",
        "--interval",
        "1m",
        "--limit",
        "100",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_backtest_runs_command():
    parser = build_parser()
    args = parser.parse_args(["backtest-runs", "--limit", "3"])

    assert args.command == "backtest-runs"
    assert args.limit == 3


def test_manage_cli_has_backtest_compare_command():
    parser = build_parser()
    args = parser.parse_args(["backtest-compare", "--limit", "5", "--export"])

    assert args.command == "backtest-compare"
    assert args.limit == 5
    assert args.export is True


def test_manage_cli_has_parameter_sweep_command():
    parser = build_parser()
    args = parser.parse_args([
        "parameter-sweep",
        "--target-profits",
        "0.0001,0.0002",
        "--trade-sizes",
        "0.05,0.10",
        "--top",
        "5",
        "--export",
    ])

    assert args.command == "parameter-sweep"
    assert args.target_profits == "0.0001,0.0002"
    assert args.trade_sizes == "0.05,0.10"
    assert args.top == 5
    assert args.export is True


def test_manage_cli_has_walk_forward_command():
    parser = build_parser()
    args = parser.parse_args(["walk-forward", "--train-size", "300", "--test-size", "100", "--export"])

    assert args.command == "walk-forward"
    assert args.train_size == 300
    assert args.test_size == 100
    assert args.export is True


def test_manage_cli_has_walk_forward_runs_command():
    parser = build_parser()
    args = parser.parse_args(["walk-forward-runs", "--limit", "3"])

    assert args.command == "walk-forward-runs"
    assert args.limit == 3


def test_manage_cli_has_backtest_periods_command():
    parser = build_parser()
    args = parser.parse_args(["backtest-periods", "1"])

    assert args.command == "backtest-periods"
    assert args.run_id == 1


def test_manage_cli_has_paper_commands():
    parser = build_parser()
    sim_args = parser.parse_args(["paper-sim", "--iterations", "2"])
    orders_args = parser.parse_args(["paper-orders", "--limit", "5"])

    assert sim_args.command == "paper-sim"
    assert sim_args.iterations == 2
    assert orders_args.command == "paper-orders"
    assert orders_args.limit == 5


def test_manage_cli_has_paper_cycle_commands():
    parser = build_parser()
    sim_args = parser.parse_args(["paper-cycle-sim", "--iterations", "3"])
    cycles_args = parser.parse_args(["paper-cycles", "--limit", "5"])
    open_cycles_args = parser.parse_args(["paper-open-cycles", "--limit", "7"])
    close_cycle_args = parser.parse_args(["paper-close-cycle", "--db-id", "9", "--reason", "stale"])
    recovery_args = parser.parse_args(["paper-recovery-action", "--db-id", "9", "--action", "resume"])
    close_watch_args = parser.parse_args([
        "paper-close-watch",
        "--profile",
        "mean_reversion_v2_small_target",
        "--interval",
        "10",
        "--max-checks",
        "3",
        "--require-binance",
        "--stop-on-close-condition",
    ])

    assert sim_args.command == "paper-cycle-sim"
    assert sim_args.iterations == 3
    assert sim_args.profile == "strict_current"
    assert cycles_args.command == "paper-cycles"
    assert cycles_args.limit == 5
    assert open_cycles_args.command == "paper-open-cycles"
    assert open_cycles_args.limit == 7
    assert close_cycle_args.command == "paper-close-cycle"
    assert close_cycle_args.db_id == 9
    assert close_cycle_args.reason == "stale"
    assert recovery_args.command == "paper-recovery-action"
    assert recovery_args.db_id == 9
    assert recovery_args.action == "resume"
    assert close_watch_args.command == "paper-close-watch"
    assert close_watch_args.profile == "mean_reversion_v2_small_target"
    assert close_watch_args.interval == 10
    assert close_watch_args.max_checks == 3
    assert close_watch_args.require_binance is True
    assert close_watch_args.stop_on_close_condition is True


def test_manage_cli_paper_cycle_accepts_strategy_profile():
    parser = build_parser()
    args = parser.parse_args([
        "paper-cycle-sim",
        "--iterations",
        "3",
        "--profile",
        "mean_reversion_v1",
        "--debug-decisions",
        "--debug-risk-details",
        "--debug-entry-zones",
        "--debug-close",
        "--force-refresh-market-data",
        "--safe-stop",
        "--resume-recovery",
    ])

    assert args.profile == "mean_reversion_v1"
    assert args.debug_decisions is True
    assert args.debug_risk_details is True
    assert args.debug_entry_zones is True
    assert args.debug_close is True
    assert args.force_refresh_market_data is True
    assert args.safe_stop is True
    assert args.resume_recovery is True


def test_manage_cli_paper_cycle_accepts_mean_reversion_v2_profile():
    parser = build_parser()
    args = parser.parse_args([
        "paper-cycle-sim",
        "--iterations",
        "3",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.profile == "mean_reversion_v2"


def test_manage_cli_paper_cycle_accepts_small_target_profile():
    parser = build_parser()
    args = parser.parse_args([
        "paper-cycle-sim",
        "--iterations",
        "3",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_accepts_hf_micro_profile_for_paper_workflow_commands():
    parser = build_parser()
    commands = [
        ["strategy-profile-sim", "--profile", "mean_reversion_hf_micro_v1"],
        ["paper-cycle-sim", "--iterations", "3", "--profile", "mean_reversion_hf_micro_v1"],
        ["long-paper-run", "--iterations", "10", "--interval", "1", "--profile", "mean_reversion_hf_micro_v1"],
        ["collect-closed-cycles", "--profile", "mean_reversion_hf_micro_v1", "--target", "5"],
        ["collect-closed-cycles", "--profile", "mean_reversion_hf_micro_v1", "--target-new", "5"],
        ["validation-summary", "--profile", "mean_reversion_hf_micro_v1"],
        ["profile-performance-summary", "--profile", "mean_reversion_hf_micro_v1"],
        ["paper-profit-concentration", "--profile", "mean_reversion_hf_micro_v1", "--since-id", "90"],
        ["paper-outlier-validation", "--profile", "mean_reversion_hf_micro_v1", "--since-id", "90"],
        ["hf-losing-cycle-diagnostics", "--profile", "mean_reversion_hf_micro_v1", "--since-id", "140", "--limit", "50"],
        ["exit-risk-diagnostics", "--profile", "mean_reversion_hf_micro_v1"],
    ]

    for command in commands:
        args = parser.parse_args(command)
        assert args.profile == "mean_reversion_hf_micro_v1"


def test_manage_cli_hf_losing_cycle_diagnostics_accepts_since_id_and_limit():
    parser = build_parser()
    args = parser.parse_args([
        "hf-losing-cycle-diagnostics",
        "--profile",
        "mean_reversion_hf_micro_v1",
        "--since-id",
        "140",
        "--limit",
        "50",
    ])

    assert args.command == "hf-losing-cycle-diagnostics"
    assert args.profile == "mean_reversion_hf_micro_v1"
    assert args.since_id == 140
    assert args.limit == 50


def test_manage_cli_has_collect_closed_cycles_command():
    parser = build_parser()
    args = parser.parse_args([
        "collect-closed-cycles",
        "--profile",
        "mean_reversion_v2_small_target",
        "--target",
        "5",
        "--interval",
        "1",
        "--max-iterations",
        "20",
        "--require-binance",
        "--print-every",
        "2",
        "--no-beep",
        "--safe-stop",
        "--resume-recovery",
        "--compact",
        "--verbose-rich",
        "--events-only",
    ])

    assert args.command == "collect-closed-cycles"
    assert args.profile == "mean_reversion_v2_small_target"
    assert args.target == 5
    assert args.target_new is None
    assert args.interval == 1
    assert args.max_iterations == 20
    assert args.require_binance is True
    assert args.print_every == 2
    assert args.beep is False
    assert args.safe_stop is True
    assert args.resume_recovery is True
    assert args.compact is True
    assert args.verbose_rich is True
    assert args.events_only is True


def test_manage_cli_has_collect_closed_cycles_target_new():
    parser = build_parser()
    args = parser.parse_args([
        "collect-closed-cycles",
        "--profile",
        "mean_reversion_hf_micro_v1",
        "--target-new",
        "50",
    ])

    assert args.command == "collect-closed-cycles"
    assert args.profile == "mean_reversion_hf_micro_v1"
    assert args.target is None
    assert args.target_new == 50


def test_manage_cli_has_long_paper_run_command():
    parser = build_parser()
    args = parser.parse_args(["long-paper-run", "--iterations", "500", "--interval", "5"])

    assert args.command == "long-paper-run"
    assert args.iterations == 500
    assert args.interval == 5
    assert args.profile == "strict_current"


def test_manage_cli_long_paper_run_accepts_strategy_profile():
    parser = build_parser()
    args = parser.parse_args([
        "long-paper-run",
        "--iterations",
        "500",
        "--interval",
        "5",
        "--profile",
        "mean_reversion_v1",
    ])

    assert args.profile == "mean_reversion_v1"


def test_manage_cli_long_paper_run_accepts_mean_reversion_v2_profile():
    parser = build_parser()
    args = parser.parse_args([
        "long-paper-run",
        "--iterations",
        "500",
        "--interval",
        "5",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.profile == "mean_reversion_v2"


def test_manage_cli_long_paper_run_accepts_small_target_profile():
    parser = build_parser()
    args = parser.parse_args([
        "long-paper-run",
        "--iterations",
        "500",
        "--interval",
        "5",
        "--profile",
        "mean_reversion_v2_small_target",
        "--debug-close",
    ])

    assert args.profile == "mean_reversion_v2_small_target"
    assert args.debug_close is True


def test_manage_cli_has_entry_threshold_sensitivity_command():
    parser = build_parser()
    args = parser.parse_args([
        "entry-threshold-sensitivity",
        "--profile",
        "mean_reversion_v1",
    ])

    assert args.command == "entry-threshold-sensitivity"
    assert args.profile == "mean_reversion_v1"


def test_manage_cli_strategy_profile_sim_accepts_small_target_profile():
    parser = build_parser()
    args = parser.parse_args([
        "strategy-profile-sim",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "strategy-profile-sim"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_micro_trend_sensitivity_command():
    parser = build_parser()
    args = parser.parse_args([
        "micro-trend-sensitivity",
        "--profile",
        "mean_reversion_v1",
    ])

    assert args.command == "micro-trend-sensitivity"
    assert args.profile == "mean_reversion_v1"


def test_manage_cli_has_target_profit_sensitivity_command():
    parser = build_parser()
    args = parser.parse_args([
        "target-profit-sensitivity",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "target-profit-sensitivity"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_exit_risk_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "exit-risk-diagnostics",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "exit-risk-diagnostics"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_max_holding_sensitivity_command():
    parser = build_parser()
    args = parser.parse_args([
        "max-holding-sensitivity",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "max-holding-sensitivity"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_exit_rule_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "exit-rule-sim",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "exit-rule-sim"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_exit_tolerance_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "exit-tolerance-sim",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "exit-tolerance-sim"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_market_session_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "market-session-diagnostics",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "market-session-diagnostics"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_session_filter_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "session-filter-sim",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "session-filter-sim"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_build_ml_dataset_command():
    parser = build_parser()
    args = parser.parse_args([
        "build-ml-dataset",
        "--symbol",
        "USDCUSDT",
        "--interval",
        "1m",
        "--limit",
        "1000",
        "--profile",
        "mean_reversion_v2_small_target",
        "--dataset-mode",
        "no_micro_trend",
    ])

    assert args.command == "build-ml-dataset"
    assert args.symbol == "USDCUSDT"
    assert args.interval == "1m"
    assert args.limit == 1000
    assert args.profile == "mean_reversion_v2_small_target"
    assert args.dataset_mode == "no_micro_trend"


def test_manage_cli_has_ml_dataset_coverage_command():
    parser = build_parser()
    args = parser.parse_args([
        "ml-dataset-coverage",
        "--symbol",
        "USDCUSDT",
        "--interval",
        "1m",
        "--limit",
        "1000",
        "--profile",
        "mean_reversion_v2_small_target",
        "--dataset-mode",
        "no_micro_trend",
    ])

    assert args.command == "ml-dataset-coverage"
    assert args.symbol == "USDCUSDT"
    assert args.interval == "1m"
    assert args.limit == 1000
    assert args.profile == "mean_reversion_v2_small_target"
    assert args.dataset_mode == "no_micro_trend"


def test_manage_cli_has_ml_dataset_summary_command():
    parser = build_parser()
    args = parser.parse_args([
        "ml-dataset-summary",
        "--file",
        "data/ml/usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv",
    ])

    assert args.command == "ml-dataset-summary"
    assert args.file == "data/ml/usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv"


def test_manage_cli_has_train_ml_baseline_command():
    parser = build_parser()
    args = parser.parse_args([
        "train-ml-baseline",
        "--file",
        "data/ml/usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv",
    ])

    assert args.command == "train-ml-baseline"
    assert args.file == "data/ml/usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv"


def test_manage_cli_has_direction_outcome_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "direction-outcome-diagnostics",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "direction-outcome-diagnostics"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_trend_alignment_commands():
    parser = build_parser()
    alignment_args = parser.parse_args([
        "trend-alignment-diagnostics",
        "--profile",
        "mean_reversion_v2_small_target",
    ])
    sim_args = parser.parse_args([
        "trend-filter-sim",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert alignment_args.command == "trend-alignment-diagnostics"
    assert alignment_args.profile == "mean_reversion_v2_small_target"
    assert sim_args.command == "trend-filter-sim"
    assert sim_args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_trend_strength_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "trend-strength-diagnostics",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "trend-strength-diagnostics"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_range_shift_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "range-shift-diagnostics",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "range-shift-diagnostics"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_target_rebase_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "target-rebase-diagnostics",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "target-rebase-diagnostics"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_break_even_rebase_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "break-even-rebase-sim",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "break-even-rebase-sim"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_holding_horizon_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "holding-horizon-diagnostics",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "holding-horizon-diagnostics"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_profile_comparison_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["profile-comparison-diagnostics"])

    assert args.command == "profile-comparison-diagnostics"


def test_manage_cli_has_post_entry_path_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "post-entry-path-diagnostics",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "post-entry-path-diagnostics"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_entry_confirmation_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "entry-confirmation-diagnostics",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "entry-confirmation-diagnostics"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_partial_target_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "partial-target-diagnostics",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "partial-target-diagnostics"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_long_paper_runs_command():
    parser = build_parser()
    args = parser.parse_args(["long-paper-runs", "--limit", "20"])

    assert args.command == "long-paper-runs"
    assert args.limit == 20


def test_manage_cli_has_paper_stats_safety_commands():
    parser = build_parser()
    stats_args = parser.parse_args(["paper-stats", "--limit", "10"])
    safety_args = parser.parse_args(["paper-safety", "--limit", "5"])

    assert stats_args.command == "paper-stats"
    assert stats_args.limit == 10
    assert safety_args.command == "paper-safety"
    assert safety_args.limit == 5


def test_manage_cli_has_paper_report_command():
    parser = build_parser()
    args = parser.parse_args(["paper-report", "--limit", "50"])

    assert args.command == "paper-report"
    assert args.limit == 50


def test_manage_cli_has_paper_recovery_state_commands():
    parser = build_parser()
    recovery_args = parser.parse_args(["paper-recovery"])
    states_args = parser.parse_args(["paper-states", "--limit", "5"])

    assert recovery_args.command == "paper-recovery"
    assert states_args.command == "paper-states"
    assert states_args.limit == 5


def test_manage_cli_has_paper_runs_command():
    parser = build_parser()
    args = parser.parse_args(["paper-runs", "--limit", "5"])

    assert args.command == "paper-runs"
    assert args.limit == 5


def test_manage_cli_has_strategy_report_command():
    parser = build_parser()
    args = parser.parse_args(["strategy-report"])

    assert args.command == "strategy-report"


def test_manage_cli_has_strategy_tuning_report_command():
    parser = build_parser()
    args = parser.parse_args(["strategy-tuning-report", "--top", "4"])

    assert args.command == "strategy-tuning-report"
    assert args.top == 4


def test_manage_cli_has_decision_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["decision-diagnostics", "--top", "3"])

    assert args.command == "decision-diagnostics"
    assert args.top == 3


def test_manage_cli_has_risk_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["risk-diagnostics", "--top", "4", "--latest", "2"])

    assert args.command == "risk-diagnostics"
    assert args.top == 4
    assert args.latest == 2


def test_manage_cli_has_risk_profitability_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["risk-profitability-diagnostics", "--limit", "7"])

    assert args.command == "risk-profitability-diagnostics"
    assert args.limit == 7


def test_manage_cli_has_fee_model_report_command():
    parser = build_parser()
    args = parser.parse_args(["fee-model-report", "--trade-size", "12.5"])

    assert args.command == "fee-model-report"
    assert args.trade_size == 12.5


def test_manage_cli_has_confidence_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["confidence-diagnostics", "--top", "4"])

    assert args.command == "confidence-diagnostics"
    assert args.top == 4


def test_manage_cli_has_entry_zone_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["entry-zone-diagnostics"])

    assert args.command == "entry-zone-diagnostics"


def test_manage_cli_has_filter_pass_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["filter-pass-diagnostics", "--latest", "3"])

    assert args.command == "filter-pass-diagnostics"
    assert args.latest == 3


def test_manage_cli_has_order_book_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["order-book-diagnostics", "--latest", "4"])

    assert args.command == "order-book-diagnostics"
    assert args.latest == 4


def test_manage_cli_has_order_book_rule_sim_command():
    parser = build_parser()
    args = parser.parse_args(["order-book-rule-sim"])

    assert args.command == "order-book-rule-sim"


def test_manage_cli_has_center_confidence_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["center-confidence-diagnostics", "--latest", "4"])

    assert args.command == "center-confidence-diagnostics"
    assert args.latest == 4


def test_manage_cli_has_center_confidence_rule_sim_command():
    parser = build_parser()
    args = parser.parse_args(["center-confidence-rule-sim", "--latest", "4"])

    assert args.command == "center-confidence-rule-sim"
    assert args.latest == 4


def test_manage_cli_has_combined_entry_rule_sim_command():
    parser = build_parser()
    args = parser.parse_args(["combined-entry-rule-sim", "--latest", "4"])

    assert args.command == "combined-entry-rule-sim"
    assert args.latest == 4


def test_manage_cli_has_strategy_profile_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "strategy-profile-sim",
        "--profile",
        "mean_reversion_v1",
        "--latest",
        "4",
    ])

    assert args.command == "strategy-profile-sim"
    assert args.profile == "mean_reversion_v1"
    assert args.latest == 4


def test_manage_cli_strategy_profile_sim_accepts_mean_reversion_v2_profile():
    parser = build_parser()
    args = parser.parse_args([
        "strategy-profile-sim",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "strategy-profile-sim"
    assert args.profile == "mean_reversion_v2"


def test_manage_cli_has_validation_summary_command():
    parser = build_parser()
    args = parser.parse_args(["validation-summary"])

    assert args.command == "validation-summary"
    assert args.profile == "strict_current"


def test_manage_cli_validation_summary_accepts_profile():
    parser = build_parser()
    args = parser.parse_args([
        "validation-summary",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "validation-summary"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_profile_performance_summary_accepts_profile():
    parser = build_parser()
    args = parser.parse_args([
        "profile-performance-summary",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "profile-performance-summary"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_paper_profit_concentration_accepts_profile_and_since_id():
    parser = build_parser()
    args = parser.parse_args([
        "paper-profit-concentration",
        "--profile",
        "mean_reversion_hf_micro_v1",
        "--since-id",
        "90",
    ])

    assert args.command == "paper-profit-concentration"
    assert args.profile == "mean_reversion_hf_micro_v1"
    assert args.since_id == 90


def test_manage_cli_paper_outlier_validation_accepts_profile_and_since_id():
    parser = build_parser()
    args = parser.parse_args([
        "paper-outlier-validation",
        "--profile",
        "mean_reversion_hf_micro_v1",
        "--since-id",
        "90",
    ])

    assert args.command == "paper-outlier-validation"
    assert args.profile == "mean_reversion_hf_micro_v1"
    assert args.since_id == 90


def test_manage_cli_exit_rule_optimizer_accepts_profile():
    parser = build_parser()
    args = parser.parse_args([
        "exit-rule-optimizer",
        "--profile",
        "mean_reversion_v2_small_target",
    ])

    assert args.command == "exit-rule-optimizer"
    assert args.profile == "mean_reversion_v2_small_target"


def test_manage_cli_has_high_frequency_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args(["high-frequency-diagnostics"])

    assert args.command == "high-frequency-diagnostics"


def test_manage_cli_has_collect_market_snapshots_command():
    parser = build_parser()
    args = parser.parse_args([
        "collect-market-snapshots",
        "--duration-hours",
        "1",
        "--interval",
        "5",
        "--max-snapshots",
        "2",
    ])

    assert args.command == "collect-market-snapshots"
    assert args.duration_hours == 1.0
    assert args.interval == 5.0
    assert args.max_snapshots == 2


def test_manage_cli_has_high_frequency_dataset_summary_command():
    parser = build_parser()
    args = parser.parse_args(["high-frequency-dataset-summary"])

    assert args.command == "high-frequency-dataset-summary"


def test_manage_cli_has_micro_cycle_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "micro-cycle-sim",
        "--scenario",
        "short_term_mean_reversion",
        "--target",
        "0.001",
        "--max-holding-seconds",
        "300",
        "--show-cycles",
    ])

    assert args.command == "micro-cycle-sim"
    assert args.scenario == "short_term_mean_reversion"
    assert args.target == 0.001
    assert args.max_holding_seconds == 300.0
    assert args.show_cycles is True


def test_manage_cli_micro_cycle_sim_accepts_custom_target():
    parser = build_parser()
    args = parser.parse_args([
        "micro-cycle-sim",
        "--scenario",
        "short_term_mean_reversion",
        "--target",
        "0.0005",
        "--max-holding-seconds",
        "180",
    ])

    assert args.command == "micro-cycle-sim"
    assert args.target == 0.0005


def test_manage_cli_micro_cycle_sim_rejects_non_positive_target():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["micro-cycle-sim", "--target", "0"])


def test_manage_cli_has_micro_cycle_grid_search_command():
    parser = build_parser()
    args = parser.parse_args([
        "micro-cycle-grid-search",
        "--scenario",
        "short_term_mean_reversion",
        "--top",
        "20",
        "--min-cycles-day",
        "100",
        "--max-drawdown",
        "0.005",
        "--export-csv",
        "reports/micro_cycle_grid_search.csv",
    ])

    assert args.command == "micro-cycle-grid-search"
    assert args.scenario == "short_term_mean_reversion"
    assert args.top == 20
    assert args.min_cycles_day == 100.0
    assert args.max_drawdown == 0.005
    assert args.export_csv == "reports/micro_cycle_grid_search.csv"


def test_manage_cli_has_hf_micro_grid_sim_command():
    parser = build_parser()
    args = parser.parse_args([
        "hf-micro-grid-sim",
        "--max-layers",
        "10",
        "--layer-size",
        "10",
        "--max-holding-seconds",
        "270",
        "--target",
        "0.0005",
        "--directional-exposure-guard",
        "--guard-min-layers",
        "2",
        "--guard-loss-threshold",
        "-0.001",
        "--show-drawdown-events",
        "--drawdown-events-limit",
        "7",
    ])

    assert args.command == "hf-micro-grid-sim"
    assert args.scenario == "short_term_mean_reversion"
    assert args.max_layers == 10
    assert args.layer_size == 10.0
    assert args.max_holding_seconds == 270.0
    assert args.target == 0.0005
    assert args.directional_exposure_guard is True
    assert args.guard_min_layers == 2
    assert args.guard_loss_threshold == -0.001
    assert args.show_drawdown_events is True
    assert args.drawdown_events_limit == 7


def test_manage_cli_has_hf_micro_grid_guard_sweep_command():
    parser = build_parser()
    args = parser.parse_args([
        "hf-micro-grid-guard-sweep",
        "--top",
        "10",
        "--min-cycles-day",
        "150",
        "--max-drawdown",
        "0.01",
        "--max-average-capital",
        "50",
        "--export-csv",
        "reports/hf_micro_grid_guard_sweep.csv",
    ])

    assert args.command == "hf-micro-grid-guard-sweep"
    assert args.top == 10
    assert args.min_cycles_day == 150.0
    assert args.max_drawdown == 0.01
    assert args.max_average_capital == 50.0
    assert args.export_csv == "reports/hf_micro_grid_guard_sweep.csv"


def test_manage_cli_has_target_resolution_compare_command():
    parser = build_parser()
    args = parser.parse_args([
        "target-resolution-diagnostics",
        "--compare",
        "0.0005",
        "0.00075",
    ])

    assert args.command == "target-resolution-diagnostics"
    assert args.compare == [0.0005, 0.00075]


def test_manage_cli_has_target_resolution_compare_simulation_command():
    parser = build_parser()
    args = parser.parse_args([
        "target-resolution-diagnostics",
        "--compare-simulation",
        "0.0005",
        "0.00075",
        "--scenario",
        "short_term_mean_reversion",
        "--max-holding-seconds",
        "270",
    ])

    assert args.command == "target-resolution-diagnostics"
    assert args.compare_simulation == [0.0005, 0.00075]
    assert args.scenario == "short_term_mean_reversion"
    assert args.max_holding_seconds == 270.0


def test_manage_cli_target_resolution_rejects_non_positive_target():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["target-resolution-diagnostics", "--compare", "0", "0.00075"])


def test_manage_cli_has_gui_command():
    parser = build_parser()
    args = parser.parse_args(["gui"])

    assert args.command == "gui"
