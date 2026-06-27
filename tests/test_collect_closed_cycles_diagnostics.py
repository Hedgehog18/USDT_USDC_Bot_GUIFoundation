from types import SimpleNamespace

from manage import (
    _collection_action_taken,
    _collection_close_reason,
    _collection_entry_diagnostics,
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


def test_collection_close_reason_filters_by_profile():
    close_debug_items = [
        {"strategy_profile": "other_profile", "close_reason": "target"},
        {"strategy_profile": "mean_reversion_hf_micro_v1", "close_reason": "max_holding_270s"},
    ]

    assert _collection_close_reason(close_debug_items, "mean_reversion_hf_micro_v1") == "max_holding_270s"
