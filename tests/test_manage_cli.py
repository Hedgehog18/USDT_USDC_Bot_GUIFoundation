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

    assert sim_args.command == "paper-cycle-sim"
    assert sim_args.iterations == 3
    assert cycles_args.command == "paper-cycles"
    assert cycles_args.limit == 5


def test_manage_cli_has_long_paper_run_command():
    parser = build_parser()
    args = parser.parse_args(["long-paper-run", "--iterations", "500", "--interval", "5"])

    assert args.command == "long-paper-run"
    assert args.iterations == 500
    assert args.interval == 5


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


def test_manage_cli_has_validation_summary_command():
    parser = build_parser()
    args = parser.parse_args(["validation-summary"])

    assert args.command == "validation-summary"


def test_manage_cli_has_gui_command():
    parser = build_parser()
    args = parser.parse_args(["gui"])

    assert args.command == "gui"
