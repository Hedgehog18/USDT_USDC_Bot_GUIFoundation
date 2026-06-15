from manage import _collection_entry_diagnostics


def test_collection_entry_diagnostics_reports_outside_session():
    diagnostics = _collection_entry_diagnostics([
        {
            "action": "WAIT",
            "reason": "mean_reversion_v2_small_target_ny: outside NEW_YORK session",
            "risk_allowed": False,
            "order_attempted": False,
        }
    ])

    assert diagnostics == {
        "entry_attempt": "no",
        "candidate_detected": "no",
        "entry_block_reason": "outside_session",
    }


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

