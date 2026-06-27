from types import SimpleNamespace

from manage import (
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
        "entry_direction": "N/A",
        "target_price": "N/A",
        "target_distance": "N/A",
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
