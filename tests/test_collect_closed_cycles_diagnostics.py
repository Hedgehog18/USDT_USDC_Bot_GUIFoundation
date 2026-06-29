from types import SimpleNamespace

from manage import (
    _apply_collection_paper_safety_block,
    _collection_action_taken,
    _collection_close_reason,
    _collection_entry_diagnostics,
    _collection_target_settings,
    _print_closed_cycle_collection_progress,
)


def test_collection_entry_diagnostics_reports_outside_session():
    diagnostics = _collection_entry_diagnostics([
        {
            "action": "WAIT",
            "reason": "mean_reversion_v2_small_target_ny: outside NEW_YORK session",
            "risk_allowed": False,
            "order_attempted": False,
        }
    ])

    assert diagnostics["entry_attempt"] == "no"
    assert diagnostics["candidate_detected"] == "no"
    assert diagnostics["entry_block_reason"] == "outside_session"


def test_collection_entry_diagnostics_reports_candidate_blocked_by_safety():
    diagnostics = _collection_entry_diagnostics([
        {
            "action": "BUY_USDC",
            "reason": "mean_reversion_v2_small_target: lower entry zone",
            "risk_allowed": False,
            "risk_reason": "Not enough notional",
            "order_attempted": False,
        }
    ])

    assert diagnostics["entry_attempt"] == "no"
    assert diagnostics["candidate_detected"] == "yes"
    assert diagnostics["entry_block_reason"] == "safety_filter"
    assert diagnostics["safety_filter_passed"] == "no"
    assert diagnostics["safety_block_reason"] == "min_notional_failed"
    assert diagnostics["safety_block_details"] == "Not enough notional"
    assert diagnostics["paper_safety_state"] == "passed"
    assert diagnostics["cooldown_check_passed"] == "N/A"


def test_collection_entry_diagnostics_reports_attempted_order():
    diagnostics = _collection_entry_diagnostics([
        {
            "action": "SELL_USDC",
            "reason": "mean_reversion_v2_small_target: upper entry zone",
            "risk_allowed": True,
            "order_attempted": True,
        }
    ])

    assert diagnostics["entry_attempt"] == "yes"
    assert diagnostics["candidate_detected"] == "yes"
    assert diagnostics["entry_block_reason"] == "no_signal"
    assert diagnostics["safety_filter_passed"] == "yes"
    assert diagnostics["balance_check_passed"] == "yes"
    assert diagnostics["open_cycle_check_passed"] == "yes"


def test_collection_entry_diagnostics_reports_spread_safety_block():
    diagnostics = _collection_entry_diagnostics([
        {
            "action": "WAIT",
            "reason": "mean_reversion_hf_micro_v1: safety_filter spread invalid",
            "risk_allowed": False,
            "order_attempted": False,
        }
    ])

    assert diagnostics["entry_block_reason"] == "safety_filter"
    assert diagnostics["safety_filter_passed"] == "no"
    assert diagnostics["safety_block_reason"] == "spread_invalid"
    assert diagnostics["spread_check_passed"] == "no"


def test_collection_entry_diagnostics_reports_existing_cycle_guard():
    diagnostics = _collection_entry_diagnostics([
        {
            "action": "WAIT",
            "reason": "database paper cycle is already open",
            "risk_allowed": False,
            "risk_reason": "Risk check skipped while database cycle is open",
            "order_attempted": False,
        }
    ])

    assert diagnostics["entry_block_reason"] == "existing_cycle"
    assert diagnostics["safety_filter_passed"] == "no"
    assert diagnostics["safety_block_reason"] == "existing_cycle"
    assert diagnostics["open_cycle_check_passed"] == "no"
    assert diagnostics["duplicate_entry_check_passed"] == "no"
    assert diagnostics["max_open_cycles_check_passed"] == "no"


def test_collection_paper_safety_block_sets_specific_diagnostics():
    diagnostics = _collection_entry_diagnostics([])

    _apply_collection_paper_safety_block(
        diagnostics,
        "Last 3 paper cycles are losing cycles.",
        {
            "paper_safety_policy": "hf_micro",
            "safety_window_scope": "new_run",
            "safety_window_cycles": "3",
            "safety_consecutive_losses": "3 / 10",
            "safety_realized_drawdown": "-0.00030000 / -0.00500000",
            "safety_timeout_loss_rate": "66.67%",
            "safety_min_cycles_met": "no",
        },
    )

    assert diagnostics["safety_filter_passed"] == "no"
    assert diagnostics["paper_safety_state"] == "blocked"
    assert diagnostics["safety_block_reason"] == "paper_max_losing_cycles"
    assert diagnostics["safety_block_details"] == "Last 3 paper cycles are losing cycles."
    assert diagnostics["paper_safety_policy"] == "hf_micro"
    assert diagnostics["safety_window_scope"] == "new_run"
    assert diagnostics["safety_consecutive_losses"] == "3 / 10"
    assert diagnostics["safety_realized_drawdown"] == "-0.00030000 / -0.00500000"
    assert diagnostics["safety_timeout_loss_rate"] == "66.67%"
    assert diagnostics["safety_min_cycles_met"] == "no"


def test_collection_entry_diagnostics_reports_short_center_readiness():
    market_state = SimpleNamespace(
        short_center=1.0001,
        price=1.0,
        hf_short_center_samples=20,
        hf_short_center_ready=True,
        hf_entry_mode="short_center",
        hf_previous_price=1.0002,
        hf_last_different_price=1.0002,
        hf_price_buffer_unique_values=2,
        hf_flat_samples_count=1,
        hf_flat_price_buffer=False,
    )

    diagnostics = _collection_entry_diagnostics([
        {
            "action": "BUY_USDC",
            "reason": "mean_reversion_hf_micro_v1: price below short_center",
            "risk_allowed": True,
            "order_attempted": True,
            "target_profit": 0.000005,
            "market_state": market_state,
        }
    ])

    assert diagnostics["short_center"] == "1.00010000"
    assert diagnostics["short_center_samples"] == "20"
    assert diagnostics["short_center_ready"] == "yes"
    assert diagnostics["hf_entry_mode"] == "short_center_direct"
    assert diagnostics["previous_price"] == "1.00020000"
    assert diagnostics["last_different_price"] == "1.00020000"
    assert diagnostics["price_buffer_unique_values"] == "2"
    assert diagnostics["flat_samples_count"] == "1"
    assert diagnostics["flat_price_buffer"] == "no"
    assert diagnostics["entry_direction"] == "BUY_USDC"
    assert diagnostics["target_price"] == "1.00000500"
    assert diagnostics["target_distance"] == "0.00000500"


def test_collection_entry_diagnostics_uses_fallback_short_center_state():
    market_state = SimpleNamespace(
        short_center=0.0,
        hf_short_center_samples=12,
        hf_short_center_ready=False,
    )

    diagnostics = _collection_entry_diagnostics([], fallback_market_state=market_state)

    assert diagnostics["short_center"] == "0.00000000"
    assert diagnostics["short_center_samples"] == "12"
    assert diagnostics["short_center_ready"] == "no"
    assert diagnostics["entry_block_reason"] == "no_short_center"


def test_collection_action_taken_uses_profile_specific_stats():
    before_stats = {"closed_cycles": 1, "open_cycles": 0}
    after_stats = {"closed_cycles": 1, "open_cycles": 0}
    result = SimpleNamespace(closed_cycles=1, opened_cycles=0)

    assert _collection_action_taken(before_stats, after_stats, result) == "waiting"


def test_collection_action_taken_reports_profile_close():
    before_stats = {"closed_cycles": 0, "open_cycles": 1}
    after_stats = {"closed_cycles": 1, "open_cycles": 0}
    result = SimpleNamespace(closed_cycles=1, opened_cycles=0)

    assert _collection_action_taken(before_stats, after_stats, result) == "closed"


def test_collection_close_reason_filters_by_profile():
    close_debug_items = [
        {"strategy_profile": "other_profile", "close_reason": "target"},
        {"strategy_profile": "mean_reversion_hf_micro_v1", "close_reason": "max_holding_270s"},
    ]

    assert _collection_close_reason(close_debug_items, "mean_reversion_hf_micro_v1") == "max_holding_270s"


def test_collection_target_settings_defaults_to_legacy_target():
    args = SimpleNamespace(target=None, target_new=None)

    assert _collection_target_settings(args) == (False, 100)


def test_collection_target_settings_uses_target_new():
    args = SimpleNamespace(target=None, target_new=50)

    assert _collection_target_settings(args) == (True, 50)


def test_collection_target_settings_rejects_target_and_target_new():
    args = SimpleNamespace(target=100, target_new=50)

    try:
        _collection_target_settings(args)
    except ValueError as exc:
        assert "--target and --target-new cannot be used together" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_collection_target_settings_rejects_non_positive_target_new():
    args = SimpleNamespace(target=None, target_new=0)

    try:
        _collection_target_settings(args)
    except ValueError as exc:
        assert "--target-new must be greater than 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_collection_progress_prints_empty_new_run(capsys):
    stats = {
        "closed_cycles": 0,
        "automatic_closed": 0,
        "manual_closed": 0,
        "target_closed": 0,
        "timeout_closed": 0,
        "open_cycles": 0,
        "net_profit": 0.0,
        "win_rate": 0.0,
    }
    entry_diagnostics = {
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
        "paper_safety_policy": "hf_micro",
        "safety_window_scope": "new_run",
        "safety_window_cycles": "3",
        "safety_consecutive_losses": "3 / 10",
        "safety_realized_drawdown": "-0.00030000 / -0.00500000",
        "safety_timeout_loss_rate": "66.67%",
        "safety_min_cycles_met": "no",
        "balance_check_passed": "N/A",
        "spread_check_passed": "N/A",
        "cooldown_check_passed": "N/A",
        "open_cycle_check_passed": "N/A",
        "duplicate_entry_check_passed": "N/A",
        "max_open_cycles_check_passed": "N/A",
        "stale_price_check_passed": "N/A",
    }

    _print_closed_cycle_collection_progress(
        stats,
        5,
        iteration=0,
        price_info=None,
        nearest_open_cycle=None,
        action_taken="waiting",
        close_reason="N/A",
        entry_diagnostics=entry_diagnostics,
        new_mode=True,
    )

    output = capsys.readouterr().out
    assert "NEW CLOSED 0 / 5" in output
    assert "new net profit: 0.00000000" in output
    assert "target closed: 0" in output
    assert "timeout closed: 0" in output
    assert "safety_filter_passed: N/A" in output
    assert "paper_safety_policy: hf_micro" in output
    assert "safety_consecutive_losses: 3 / 10" in output
    assert "safety_realized_drawdown: -0.00030000 / -0.00500000" in output
    assert "safety_timeout_loss_rate: 66.67%" in output
    assert "cooldown_check_passed: N/A" in output
    assert "stale_price_check_passed: N/A" in output
