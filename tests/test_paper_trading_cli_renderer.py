from types import SimpleNamespace

from paper.paper_analytics_engine import PaperAnalytics
from paper.paper_trading_cli_renderer import PaperTradingCliRenderer


def _stats() -> PaperAnalytics:
    return PaperAnalytics(
        total_cycles=5,
        closed_cycles=4,
        winning_cycles=2,
        losing_cycles=1,
        win_rate=0.5,
        gross_profit=0.01,
        net_profit=0.02,
        average_net_profit=0.005,
        profit_factor=2.0,
        breakeven_cycles=1,
        average_profit=0.02,
        average_loss=-0.01,
        average_cycle_pnl=0.005,
        expectancy=0.005,
        timeout_closed=2,
        timeout_profit_cycles=1,
        timeout_breakeven_cycles=0,
        timeout_loss_cycles=1,
        timeout_average_pnl=-0.001,
        timeout_max_profit=0.003,
        timeout_max_loss=-0.005,
        target_closed=2,
        target_total_profit=0.03,
        target_average_profit=0.015,
        buy_count=2,
        buy_total_pnl=0.01,
        buy_average_pnl=0.005,
        buy_win_rate=0.5,
        sell_count=2,
        sell_total_pnl=0.01,
        sell_average_pnl=0.005,
        sell_win_rate=0.5,
    )


def test_renderer_prints_paper_stats_without_rich(capsys):
    PaperTradingCliRenderer(force_plain=True).render_paper_stats(_stats())

    output = capsys.readouterr().out

    assert "PAPER TRADING STATS" in output
    assert "Net Profit: +0.02000000" in output
    assert "Timeout Profit: 1" in output
    assert "BUY Win Rate: 50.00%" in output


def test_renderer_hides_na_collection_fields(capsys):
    stats = {
        "closed_cycles": 0,
        "automatic_closed": 0,
        "manual_closed": 0,
        "target_closed": 0,
        "timeout_closed": 0,
        "open_cycles": 0,
        "net_profit": 0.0,
        "win_rate": 0.0,
        "winning_cycles": 0,
        "breakeven_cycles": 0,
        "losing_cycles": 0,
        "net_profit_without_extreme": 0.0,
        "extreme_profit": 0.0,
        "extreme_cycles": 0,
        "non_extreme_cycles": 0,
        "win_rate_without_extreme": 0.0,
    }
    diagnostics = {
        "candidate_detected": "no",
        "entry_block_reason": "no_signal",
        "short_center": "N/A",
        "short_center_samples": "N/A",
        "hf_entry_mode": "N/A",
        "entry_direction": "N/A",
        "target_price": "N/A",
        "target_distance": "N/A",
        "safety_filter_passed": "N/A",
        "safety_block_reason": "N/A",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress_compact(
        stats,
        5,
        iteration=0,
        price_info=None,
        nearest_open_cycle=None,
        action_taken="waiting",
        entry_diagnostics=diagnostics,
    )

    output = capsys.readouterr().out

    assert "New: 0/5" in output
    assert "Lifetime: 0" in output
    assert "Open: 0" in output
    assert "New Profit: +0.00000000" in output
    assert "New Profit NoExt: +0.00000000" in output
    assert "New Extreme Profit: +0.00000000" in output
    assert "Extreme: 0" in output
    assert "Lifetime Profit: +0.00000000" in output
    assert "New Win: 0.00%" in output
    assert "New Win NoExt: 0.00%" in output
    assert " | Profit:" not in output
    assert " | Win:" not in output
    assert "Block: no_signal" in output
    assert "CURRENT COLLECTION DIRECTION BREAKDOWN" not in output
    assert "CURRENT COLLECTION CLOSE BREAKDOWN" not in output
    assert "No open cycle" not in output
    assert "safety_filter_passed" not in output
    assert "N/A" not in output


def test_renderer_prints_open_cycle(capsys):
    open_cycle = SimpleNamespace(
        db_id=10,
        direction="SELL_USDC",
        current_price=1.0009,
        target_price=1.0008,
        distance_to_target=0.0001,
        unrealized_pnl=-0.0002,
        age_seconds=168,
        close_condition_met=False,
    )
    stats = {
        "closed_cycles": 1,
        "open_cycles": 1,
        "net_profit": 0.001,
        "win_rate": 1.0,
        "net_profit_without_extreme": -0.0001,
        "extreme_profit": 0.0011,
        "extreme_cycles": 1,
        "non_extreme_cycles": 1,
        "win_rate_without_extreme": 0.0,
    }
    diagnostics = {
        "candidate_detected": "no",
        "entry_block_reason": "existing_cycle",
        "short_center": "1.00085000",
        "short_center_samples": "60",
        "hf_entry_mode": "short_center",
        "entry_direction": "N/A",
        "target_price": "N/A",
        "target_distance": "N/A",
        "safety_filter_passed": "N/A",
        "safety_block_reason": "N/A",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress_compact(
        stats,
        5,
        iteration=2,
        price_info=(1.0009, "BINANCE", "2026-07-01T10:00:00"),
        nearest_open_cycle=open_cycle,
        action_taken="waiting",
        entry_diagnostics=diagnostics,
        lifetime_stats={"closed_cycles": 12, "net_profit": 0.02, "win_rate": 0.5},
        collection_id="test-collection",
        tracking_limit_seconds=270,
    )

    output = capsys.readouterr().out

    assert "Cycle: SELL_USDC" in output
    assert "collection test-collection" in output
    assert "Lifetime: 12" in output
    assert "New Profit: +0.00100000" in output
    assert "New Profit NoExt: -0.00010000" in output
    assert "New Extreme Profit: +0.00110000" in output
    assert "Extreme: 1" in output
    assert "NonExt: 1" in output
    assert "Lifetime Profit: +0.02000000" in output
    assert "New Win: 100.00%" in output
    assert "New Win NoExt: 0.00%" in output
    assert "uPnL: -0.00020000" in output
    assert "Tracking: 2m 48s / 4m 30s" in output
    assert "Age:" not in output


def test_renderer_prints_extreme_open_signal_metrics(capsys):
    open_cycle = SimpleNamespace(
        db_id=11,
        direction="SELL_USDC",
        current_price=1.0008,
        target_price=1.0007,
        distance_to_target=0.0001,
        unrealized_pnl=-0.0001,
        age_seconds=1,
    )
    stats = {
        "closed_cycles": 0,
        "open_cycles": 1,
        "net_profit": 0.0,
        "win_rate": 0.0,
    }
    diagnostics = {
        "extreme_signal_detected": "yes",
        "session_signal": "yes",
        "velocity_spike_signal": "yes",
        "price_velocity": "-0.00000200",
        "velocity_threshold": "0.00000100",
        "compression_signal": "yes",
        "compression_score": "100.00000000",
        "compression_threshold": "60.00000000",
        "signal_strength": "100.00000000",
        "expected_direction": "SELL_USDC",
        "lead_time_warning": "yes",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress_compact(
        stats,
        5,
        iteration=1,
        price_info=(1.0008, "BINANCE", "2026-07-01T10:00:00"),
        nearest_open_cycle=open_cycle,
        action_taken="opened",
        entry_diagnostics=diagnostics,
    )

    output = capsys.readouterr().out

    assert "Extreme: signal=yes" in output
    assert "velocity_value=-0.00000200/0.00000100" in output
    assert "compression_score=100.00000000/60.00000000" in output


def test_renderer_prints_closed_cycle_details(capsys):
    stats = {
        "closed_cycles": 1,
        "open_cycles": 0,
        "net_profit": 0.0,
        "win_rate": 0.0,
    }
    last_closed_cycle = {
        "db_id": 42,
        "profile": "extreme_strategy_v1",
        "direction": "SELL_USDC",
        "open_price": 1.000825,
        "close_price": 1.000825,
        "target_price": 1.000815,
        "net_profit": 0.0,
        "close_reason": "extreme_timeout",
        "holding_seconds": 60.0,
        "target_hit": "no",
        "timeout_hit": "yes",
        "distance_to_target_at_close": 0.00001,
        "was_extreme_close": "no",
        "breakeven_close": "yes",
        "possible_reason": "timeout_at_entry_price",
        "extreme_signal_at_entry": "yes",
        "entry_signal_strength": 80.0,
        "entry_velocity_value": -0.000002,
        "entry_velocity_threshold": 0.000001,
        "entry_compression_score": 100.0,
        "entry_compression_threshold": 60.0,
        "expected_direction": "SELL_USDC",
        "lead_warning": "yes",
        "false_positive_hint": "late_entry",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress_compact(
        stats,
        3,
        iteration=4,
        price_info=(1.000825, "BINANCE", "2026-07-01T10:00:00"),
        nearest_open_cycle=None,
        action_taken="closed",
        last_closed_cycle=last_closed_cycle,
        entry_diagnostics={},
    )

    output = capsys.readouterr().out

    assert "Closed Cycle: db_id=42" in output
    assert "profile=extreme_strategy_v1" in output
    assert "reason=extreme_timeout" in output
    assert "net=+0.00000000" in output
    assert "open=1.00082500" in output
    assert "close=1.00082500" in output
    assert "target=1.00081500" in output
    assert "holding=1m 0s" in output
    assert "target_hit=no" in output
    assert "timeout_hit=yes" in output
    assert "breakeven_close=yes" in output
    assert "possible_reason=timeout_at_entry_price" in output
    assert "Extreme Entry: signal=yes" in output
    assert "velocity=-0.00000200/0.00000100" in output
    assert "false_positive_hint=late_entry" in output


def test_renderer_closed_cycle_hf_v1_does_not_print_extreme_entry(capsys):
    stats = {
        "closed_cycles": 1,
        "open_cycles": 0,
        "net_profit": 0.0001,
        "win_rate": 1.0,
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress_compact(
        stats,
        3,
        iteration=4,
        price_info=(1.000825, "BINANCE", "2026-07-01T10:00:00"),
        nearest_open_cycle=None,
        action_taken="closed",
        last_closed_cycle={
            "db_id": 43,
            "profile": "mean_reversion_hf_micro_v1",
            "direction": "BUY_USDC",
            "open_price": 1.000825,
            "close_price": 1.000835,
            "target_price": 1.000835,
            "net_profit": 0.0001,
            "close_reason": "target",
            "holding_seconds": 10.0,
            "target_hit": "yes",
            "timeout_hit": "no",
            "distance_to_target_at_close": 0.0,
            "was_extreme_close": "no",
            "breakeven_close": "no",
            "possible_reason": "N/A",
        },
        entry_diagnostics={},
    )

    output = capsys.readouterr().out

    assert "Closed Cycle: db_id=43" in output
    assert "profile=mean_reversion_hf_micro_v1" in output
    assert "Extreme Entry:" not in output


def test_renderer_verbose_progress_keeps_full_panels(capsys):
    stats = {
        "closed_cycles": 1,
        "open_cycles": 0,
        "net_profit": 0.001,
        "win_rate": 1.0,
        "target_closed": 1,
        "timeout_closed": 0,
        "manual_closed": 0,
        "buy_count": 1,
        "buy_total_pnl": 0.001,
        "buy_win_rate": 1.0,
        "sell_count": 0,
    }
    diagnostics = {
        "candidate_detected": "yes",
        "entry_block_reason": "N/A",
        "short_center": "1.00085000",
        "short_center_samples": "60",
        "hf_entry_mode": "short_center",
        "entry_direction": "BUY_USDC",
        "target_price": "1.00090000",
        "target_distance": "0.00005000",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress(
        stats,
        5,
        iteration=3,
        price_info=(1.00085, "BINANCE", "2026-07-01T10:00:00"),
        nearest_open_cycle=None,
        action_taken="opened",
        close_reason="N/A",
        entry_diagnostics=diagnostics,
        lifetime_stats={"closed_cycles": 12, "net_profit": 0.02, "win_rate": 0.5},
        collection_id="test-collection",
        profile="mean_reversion_hf_micro_v1",
    )

    output = capsys.readouterr().out

    assert "PAPER TRADING STATUS" in output
    assert "CURRENT COLLECTION PERFORMANCE" in output
    assert "LIFETIME SUMMARY" in output
    assert "CURRENT COLLECTION CLOSE BREAKDOWN" in output
    assert "CURRENT COLLECTION DIRECTION BREAKDOWN" in output


def test_renderer_prints_collection_summary(capsys):
    stats = {
        "closed_cycles": 5,
        "automatic_closed": 5,
        "target_closed": 3,
        "timeout_closed": 2,
        "timeout_profit": 1,
        "timeout_breakeven": 0,
        "timeout_loss": 1,
        "zero_net_cycles": 1,
        "extreme_target_closed": 2,
        "extreme_timeout_closed": 1,
        "manual_closed": 0,
        "net_profit": 0.01,
        "net_profit_without_extreme": 0.002,
        "extreme_profit": 0.008,
        "extreme_cycles": 1,
        "non_extreme_cycles": 4,
        "extreme_profit_share": 0.8,
        "win_rate_without_extreme": 0.5,
        "extreme_recommendation": "MODERATE_EXTREME_IMPACT_RUN",
        "extreme_warning": "WARNING: New run is extreme-dependent. Do not evaluate ordinary HF performance using raw New Profit.",
        "win_rate": 0.6,
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_summary(
        stats,
        lifetime_stats={"closed_cycles": 100, "net_profit": 0.123, "win_rate": 0.64},
        collection_id="collection-1",
        profile="mean_reversion_hf_micro_v1",
    )

    output = capsys.readouterr().out

    assert "NEW COLLECTION SUMMARY" in output
    assert "Collection ID: collection-1" in output
    assert "New timeout profit: 1" in output
    assert "New breakeven closed: 0" in output
    assert "New zero-net cycles: 1" in output
    assert "New extreme_target closed: 2" in output
    assert "New extreme_timeout closed: 1" in output
    assert "New net profit without extreme: +0.00200000" in output
    assert "New extreme profit: +0.00800000" in output
    assert "New extreme cycles: 1" in output
    assert "New non-extreme cycles: 4" in output
    assert "Extreme profit share: 80.00%" in output
    assert "New win rate without extreme: 50.00%" in output
    assert "EXTREME RUN WARNING" in output
    assert "Recommendation: MODERATE_EXTREME_IMPACT_RUN" in output
    assert "New win rate: 60.00%" in output
    assert "Lifetime closed cycles: 100" in output


def test_renderer_prints_recovery_required_warning(capsys):
    PaperTradingCliRenderer(force_plain=True).render_recovery_required(
        "Open cycle detected from previous session. Automatic close is disabled.",
        cycle={
            "db_id": 9,
            "direction": "BUY_USDC",
            "open_price": 1.0001,
            "target_price": 1.0002,
            "current_price": 1.00015,
            "distance_to_target": 0.00005,
            "target_status": "not reached",
            "estimated_pnl_now": 0.0005,
            "decision_hint": "target not reached / estimated profit if closed now",
            "opened_session_id": "old-session",
            "current_session_id": "current-session",
            "opened_at": "2026-07-01T09:00:00",
            "elapsed": "3h 2m",
            "recovery_status": "RECOVERY_REQUIRED",
        },
    )

    output = capsys.readouterr().out

    assert "RECOVERY REQUIRED" in output
    assert "Open cycle detected from previous session" in output
    assert "DB ID: 9" in output
    assert "Current Price: 1.00015000" in output
    assert "Distance Target: 0.00005000" in output
    assert "Target Status: not reached" in output
    assert "Est. PnL Now: +0.00050000" in output
    assert "Decision Hint: target not reached / estimated profit if closed now" in output
    assert "Elapsed since opened: 3h 2m" in output
    assert "Active tracking: paused" in output
    assert "Automatic close: DISABLED" in output
    assert "paper-recovery-action --db-id 9 --action resume" in output
    assert "paper-close-cycle --db-id 9 --reason manual" in output
    assert "paper-recovery-action --db-id 9 --action abandon --reason stale" in output


def test_renderer_prints_recovery_unavailable_price(capsys):
    PaperTradingCliRenderer(force_plain=True).render_recovery_required(
        "Open cycle detected from previous session. Automatic close is disabled.",
        cycle={
            "db_id": 9,
            "direction": "BUY_USDC",
            "open_price": 1.0001,
            "target_price": 1.0002,
            "current_price": None,
            "distance_to_target": None,
            "target_status": "unknown",
            "estimated_pnl_now": None,
            "decision_hint": "current price unavailable / choose recovery action manually",
            "opened_session_id": "old-session",
            "current_session_id": "current-session",
            "opened_at": "2026-07-01T09:00:00",
            "elapsed": "3h 2m",
            "recovery_status": "RECOVERY_REQUIRED",
        },
    )

    output = capsys.readouterr().out

    assert "Current Price: unavailable" in output
    assert "Distance Target: unavailable" in output
    assert "Est. PnL Now: unavailable" in output
    assert "Target Status: unknown" in output
