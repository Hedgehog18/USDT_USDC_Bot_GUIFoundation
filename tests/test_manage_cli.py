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

    assert sim_args.command == "paper-cycle-sim"
    assert sim_args.iterations == 3
    assert sim_args.profile == "strict_current"
    assert cycles_args.command == "paper-cycles"
    assert cycles_args.limit == 5
    assert open_cycles_args.command == "paper-open-cycles"
    assert open_cycles_args.limit == 7


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
    ])

    assert args.profile == "mean_reversion_v1"
    assert args.debug_decisions is True
    assert args.debug_risk_details is True
    assert args.debug_entry_zones is True
    assert args.debug_close is True
    assert args.force_refresh_market_data is True


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


def test_manage_cli_has_direction_outcome_diagnostics_command():
    parser = build_parser()
    args = parser.parse_args([
        "direction-outcome-diagnostics",
        "--profile",
        "mean_reversion_v2",
    ])

    assert args.command == "direction-outcome-diagnostics"
    assert args.profile == "mean_reversion_v2"


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


def test_manage_cli_has_gui_command():
    parser = build_parser()
    args = parser.parse_args(["gui"])

    assert args.command == "gui"
