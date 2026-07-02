from types import SimpleNamespace

from manage import (
    _apply_collection_tracking_age,
    _apply_collection_paper_safety_block,
    _collection_action_taken,
    _collection_close_reason,
    _collection_entry_diagnostics,
    _collection_recovery_cycle_from_row,
    _collection_target_settings,
    _enrich_collection_recovery_cycle,
    _find_collection_recovery_cycle,
    _load_recovery_current_price_info,
    _print_closed_cycle_collection_event,
    command_collect_closed_cycles,
    _print_closed_cycle_collection_progress,
    _should_print_collection_progress,
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


def test_collection_progress_throttle_respects_interval():
    assert _should_print_collection_progress(None, 100.0, 60.0) is True
    assert _should_print_collection_progress(100.0, 159.9, 60.0) is False
    assert _should_print_collection_progress(100.0, 160.0, 60.0) is True


def test_collection_tracking_age_uses_runtime_monotonic_mapping():
    open_cycle = SimpleNamespace(db_id=42, age_seconds=180 * 60)

    updated = _apply_collection_tracking_age(open_cycle, {42: 100.0}, 160.0)

    assert updated.age_seconds == 60.0


def test_collection_tracking_age_keeps_cycle_when_not_observed():
    open_cycle = SimpleNamespace(db_id=42, age_seconds=180 * 60)

    updated = _apply_collection_tracking_age(open_cycle, {}, 160.0)

    assert updated.age_seconds == 180 * 60


def test_collection_events_only_prints_open_event(capsys):
    open_cycle = SimpleNamespace(
        direction="BUY_USDC",
        db_id=1201,
        open_price=1.000665,
        target_price=1.000670,
    )

    _print_closed_cycle_collection_event(
        action_taken="opened",
        close_reason="N/A",
        close_debug_items=[],
        nearest_open_cycle=open_cycle,
        result=SimpleNamespace(recovery_required=False, safety_stops=0),
    )

    output = capsys.readouterr().out

    assert "OPEN BUY_USDC" in output
    assert "db_id=1201" in output
    assert "price=1.00066500" in output
    assert "target=1.00067000" in output


def test_collection_events_only_prints_close_event(capsys):
    _print_closed_cycle_collection_event(
        action_taken="closed",
        close_reason="max_holding_270s",
        close_debug_items=[{"db_id": 1202, "close_attempted": True, "close_result": "CLOSED"}],
        nearest_open_cycle=None,
        result=SimpleNamespace(recovery_required=False, safety_stops=0),
    )

    output = capsys.readouterr().out

    assert "CLOSE TIMEOUT" in output
    assert "db_id=1202" in output


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

    assert _collection_target_settings(args) == (True, 100)


def test_collection_target_settings_uses_target_new():
    args = SimpleNamespace(target=None, target_new=50)

    assert _collection_target_settings(args) == (True, 50)


def test_collection_target_settings_uses_target_as_new_collection_goal():
    args = SimpleNamespace(target=500, target_new=None)

    assert _collection_target_settings(args) == (True, 500)


def test_collection_target_reached_uses_new_stats_not_lifetime():
    from manage import _collection_target_reached

    lifetime_stats = {"closed_cycles": 1132}
    current_collection_stats = {"closed_cycles": 0}

    assert _collection_target_reached(
        lifetime_stats,
        current_collection_stats,
        500,
        new_mode=True,
    ) is False


def _open_recovery_row(*, db_id=9, opened_session_id="old-session", recovery_status="ACTIVE"):
    return (
        db_id,
        "2026-07-01T10:00:00",
        db_id,
        "mean_reversion_hf_micro_v1",
        "BUY_USDC",
        "OPEN",
        1.0001,
        1.0002,
        10.0,
        0.0,
        0.0,
        0.0,
        0.0,
        "2026-07-01T09:00:00",
        None,
        opened_session_id,
        recovery_status,
    )


def test_collection_recovery_cycle_detects_old_open_cycle():
    cycle = _collection_recovery_cycle_from_row(
        _open_recovery_row(opened_session_id="old-session"),
        "current-session",
    )

    assert cycle["db_id"] == 9
    assert cycle["direction"] == "BUY_USDC"
    assert cycle["opened_session_id"] == "old-session"
    assert cycle["current_session_id"] == "current-session"


def test_collection_recovery_cycle_ignores_current_session_open_cycle():
    cycle = _collection_recovery_cycle_from_row(
        _open_recovery_row(opened_session_id="current-session"),
        "current-session",
    )

    assert cycle is None


def test_collection_recovery_cycle_ignores_resume_requested_cycle():
    cycle = _collection_recovery_cycle_from_row(
        _open_recovery_row(recovery_status="RESUME_REQUESTED"),
        "current-session",
    )

    assert cycle is None


def test_find_collection_recovery_cycle_marks_database_cycle():
    class FakeDatabase:
        def __init__(self):
            self.marked = []

        def load_open_paper_cycles_with_recovery(self, limit=1000):
            return [_open_recovery_row(db_id=42)]

        def mark_paper_cycle_recovery_required(self, db_id):
            self.marked.append(db_id)
            return True

    database = FakeDatabase()

    cycle = _find_collection_recovery_cycle(database, "current-session")

    assert cycle["db_id"] == 42
    assert cycle["recovery_status"] == "RECOVERY_REQUIRED"
    assert database.marked == [42]


def test_collection_recovery_cycle_enrichment_calculates_current_price_and_pnl(monkeypatch):
    config = SimpleNamespace(
        symbol="USDCUSDT",
        maker_fee_percent=0.001,
        taker_fee_percent=0.001,
    )
    cycle = _collection_recovery_cycle_from_row(
        _open_recovery_row(opened_session_id="old-session"),
        "current-session",
    )

    monkeypatch.setattr(
        "manage._load_recovery_current_price_info",
        lambda config, database: (1.00015, "BINANCE", "2026-07-01T10:05:00"),
    )

    enriched = _enrich_collection_recovery_cycle(config, object(), cycle)

    assert enriched["current_price"] == 1.00015
    assert abs(enriched["distance_to_target"] - 0.00005) < 0.000000001
    assert enriched["target_status"] == "not reached"
    assert round(enriched["estimated_pnl_now"], 8) == 0.0005
    assert enriched["decision_hint"] == "target not reached / estimated profit if closed now"


def test_collection_recovery_cycle_enrichment_handles_unavailable_price(monkeypatch):
    config = SimpleNamespace(
        symbol="USDCUSDT",
        maker_fee_percent=0.001,
        taker_fee_percent=0.001,
    )
    cycle = _collection_recovery_cycle_from_row(
        _open_recovery_row(opened_session_id="old-session"),
        "current-session",
    )

    monkeypatch.setattr("manage._load_recovery_current_price_info", lambda config, database: None)

    enriched = _enrich_collection_recovery_cycle(config, object(), cycle)

    assert enriched["current_price"] is None
    assert enriched["distance_to_target"] is None
    assert enriched["estimated_pnl_now"] is None
    assert enriched["target_status"] == "unknown"
    assert "current price unavailable" in enriched["decision_hint"]


def test_recovery_price_info_returns_none_when_fetch_fails():
    class FakeDatabase:
        def connect(self):
            raise RuntimeError("database unavailable")

    config = SimpleNamespace(symbol="USDCUSDT")

    assert _load_recovery_current_price_info(config, FakeDatabase()) is None


def test_collect_closed_cycles_stops_before_progress_when_recovery_exists(monkeypatch, capsys):
    class FakeLogger:
        def debug(self, *args, **kwargs):
            return None

    class FakeDatabase:
        def load_paper_cycle_collection_baseline(self, profile):
            return {"max_cycle_id": 42, "closed_cycles": 1132, "net_profit": 0.1}

        def load_open_paper_cycles_with_recovery(self, limit=1000):
            return [_open_recovery_row(db_id=77, opened_session_id="old-session")]

        def mark_paper_cycle_recovery_required(self, db_id):
            self.marked = db_id
            return True

    def fail_engine(*args, **kwargs):
        raise AssertionError("PaperTradingEngine must not start in early recovery mode")

    config = SimpleNamespace(symbol="USDCUSDT", maker_fee_percent=0.001, taker_fee_percent=0.001)

    monkeypatch.setattr("manage.build_context", lambda: (config, FakeLogger(), FakeDatabase()))
    monkeypatch.setattr("manage._ensure_profile_allowed_for_paper", lambda config, profile: None)
    monkeypatch.setattr(
        "manage._load_recovery_current_price_info",
        lambda config, database: (1.0002, "BINANCE", "2026-07-01T10:05:00"),
    )
    monkeypatch.setattr("manage.PaperTradingEngine", fail_engine)

    args = SimpleNamespace(
        profile="mean_reversion_hf_micro_v1",
        target=500,
        target_new=None,
        interval=0,
        progress_interval=60.0,
        max_iterations=1,
        print_every=1,
        safe_stop=False,
        beep=False,
        require_binance=False,
        events_only=False,
        verbose_rich=False,
        resume_recovery=False,
    )

    command_collect_closed_cycles(args)

    output = capsys.readouterr().out
    assert "RECOVERY REQUIRED" in output
    assert "DB ID" in output
    assert "77" in output
    assert "paper-recovery-action" in output
    assert "paper-close-cycle" in output
    assert "--db-id 77" in output
    assert "--action resume" in output
    assert "--action abandon" in output
    assert "--reason" in output
    assert "manual" in output
    assert "stale" in output
    assert "Current Price" in output
    assert "1.00020000" in output
    assert "Distance Target" in output
    assert "reached" in output
    assert "Est. PnL Now" in output
    assert "Decision Hint" in output
    assert "New:" not in output
    assert "Cycle:" not in output


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
    assert "New: 0/5" in output
    assert "Lifetime: 0" in output
    assert "Open: 0" in output
    assert "New Profit: +0.00000000" in output
    assert "Lifetime Profit: +0.00000000" in output
    assert "Block: no_signal" in output
    assert "CURRENT COLLECTION PERFORMANCE" not in output
    assert "LIFETIME SUMMARY" not in output
    assert "No open cycle" not in output
    assert "no_signal" in output
    assert "cooldown_check_passed" not in output
    assert "stale_price_check_passed" not in output
