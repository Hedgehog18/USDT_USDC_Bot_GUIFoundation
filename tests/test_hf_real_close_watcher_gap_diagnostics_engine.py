import json
from datetime import datetime, timedelta, timezone

import pytest

from analytics.hf_real_close_watcher_gap_diagnostics_engine import (
    HFRealCloseWatcherGapDiagnosticsEngine,
    _seconds_between,
    normalize_diagnostic_datetime,
)
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _real_cycle(
    database: DatabaseManager,
    *,
    db_id: int = 25,
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> None:
    opened_at = opened_at or datetime(2026, 7, 20, 18, 20, 16, 386298)
    closed_at = closed_at or opened_at + timedelta(seconds=273)
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_cycles (
                id, timestamp, strategy_profile, symbol, direction, status,
                open_price, close_price, quantity, stake_usdt, gross_profit,
                net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
            ) VALUES (?, ?, ?, 'USDCUSDT', 'BUY_USDC', 'CLOSED',
                1.00068000, 1.00064000, 5, 6, -0.0002, -0.0002,
                ?, ?, 'max_holding_270s', 'entry-order', 'run-25')
            """,
            (db_id, opened_at.isoformat(), PROFILE, opened_at.isoformat(), closed_at.isoformat()),
        )
        conn.commit()


def _order_event(
    database: DatabaseManager,
    *,
    timestamp: datetime,
    run_id: str,
    side: str,
    status: str,
    close_cycle_id: int | None = None,
    close_reason: str | None = None,
) -> None:
    request = {"symbol": "USDCUSDT", "side": side, "type": "MARKET", "quantity": "5"}
    if close_cycle_id is not None:
        request["close_cycle_id"] = close_cycle_id
    if close_reason is not None:
        request["close_reason"] = close_reason
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_order_events (
                timestamp, run_id, strategy_profile, symbol, side, quantity,
                status, request_payload, response_payload, error
            ) VALUES (?, ?, ?, 'USDCUSDT', ?, 5, ?, ?, ?, NULL)
            """,
            (
                timestamp.isoformat(),
                run_id,
                PROFILE,
                side,
                status,
                json.dumps(request),
                json.dumps({"status": status, "executedQty": "5"}),
            ),
        )
        conn.commit()


def _snapshot(
    database: DatabaseManager,
    *,
    cycle_id: int,
    timestamp: datetime,
    phase: str,
    price: float,
    bid: float,
    ask: float,
    source: str,
    raw_payload: dict | None = None,
) -> None:
    database.save_real_pilot_market_snapshot(
        real_cycle_id=cycle_id,
        campaign_id="campaign-25",
        timestamp=timestamp.isoformat(),
        phase=phase,
        symbol="USDCUSDT",
        price=price,
        bid=bid,
        ask=ask,
        mid=(bid + ask) / 2,
        spread=ask - bid,
        short_center=1.000715 if phase == "entry" else None,
        hf_entry_mode="short_center" if phase == "entry" else None,
        candidate=True if phase == "entry" else None,
        block_reason="N/A" if phase == "entry" else None,
        direction="BUY_USDC",
        target_price=1.0006850034,
        distance_to_target=1.0006850034 - bid,
        unrealized_pnl=None,
        open_real_cycles=1,
        source=source,
        raw_payload_json=json.dumps(raw_payload) if raw_payload is not None else None,
    )


def test_close_watcher_gap_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFRealCloseWatcherGapDiagnosticsEngine(database).build_report(PROFILE)

    assert report.cycles_analyzed == 0
    assert report.executable_touches == 0
    assert report.immediate_checks_performed == 0
    assert report.immediate_target_triggers == 0
    assert report.regular_watcher_triggers == 0
    assert report.missed_executable_touches == 0
    assert report.recommendation == "NO_EXECUTABLE_TOUCHES_FOUND"


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (datetime(2026, 7, 20, 18, 20, 16), datetime(2026, 7, 20, 18, 20, 17, tzinfo=timezone.utc), 1.0),
        (datetime(2026, 7, 20, 18, 20, 16, tzinfo=timezone.utc), datetime(2026, 7, 20, 18, 20, 17), 1.0),
        (datetime(2026, 7, 20, 18, 20, 16), datetime(2026, 7, 20, 18, 20, 18), 2.0),
        ("2026-07-20T20:20:16+02:00", "2026-07-20T18:20:19+00:00", 3.0),
        ("2026-07-20T18:20:16", "2026-07-20T18:20:20", 4.0),
        ("2026-07-20T18:20:16Z", "2026-07-20T18:20:21Z", 5.0),
        ("2026-07-20T18:20:16+00:00", "2026-07-20T18:20:22+00:00", 6.0),
    ],
)
def test_diagnostic_datetime_normalization_seconds_between(start, end, expected):
    assert _seconds_between(start, end) == pytest.approx(expected)
    assert normalize_diagnostic_datetime(start).tzinfo is not None
    assert normalize_diagnostic_datetime(end).tzinfo is not None


def test_diagnostic_datetime_normalization_handles_missing_timestamp():
    assert _seconds_between(None, "2026-07-20T18:20:16Z") is None
    assert _seconds_between("2026-07-20T18:20:16Z", None) is None


def test_close_watcher_gap_detects_db25_shape_blind_window(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened = datetime(2026, 7, 20, 18, 20, 16, 386298)
    filled = opened - timedelta(milliseconds=10)
    first_check = opened + timedelta(seconds=5, microseconds=573270)
    _real_cycle(database, opened_at=opened)
    _order_event(database, timestamp=opened - timedelta(seconds=1), run_id="run-25", side="BUY", status="ATTEMPTED")
    _order_event(database, timestamp=filled, run_id="run-25", side="BUY", status="FILLED")
    _snapshot(
        database,
        cycle_id=25,
        timestamp=opened + timedelta(milliseconds=24),
        phase="entry",
        price=1.000695,
        bid=1.000690,
        ask=1.000700,
        source="BINANCE",
    )
    _snapshot(
        database,
        cycle_id=25,
        timestamp=first_check,
        phase="tracking",
        price=1.000670,
        bid=1.000670,
        ask=1.000680,
        source="real_pilot_close_watch",
    )
    _order_event(
        database,
        timestamp=opened + timedelta(seconds=272),
        run_id="close-25",
        side="SELL",
        status="ATTEMPTED_CLOSE",
        close_cycle_id=25,
        close_reason="max_holding_270s",
    )
    _order_event(
        database,
        timestamp=opened + timedelta(seconds=273),
        run_id="close-25",
        side="SELL",
        status="FILLED",
        close_cycle_id=25,
        close_reason="max_holding_270s",
    )

    report = HFRealCloseWatcherGapDiagnosticsEngine(database).build_report(PROFILE, real_cycle_id=25)

    assert report.cycles_analyzed == 1
    assert report.executable_touches == 1
    assert report.missed_executable_touches == 1
    assert report.recommendation == "BLIND_WINDOW_REQUIRES_REVIEW"
    assert report.cycle_report is not None
    assert report.cycle_report.executable_target_touched is True
    assert report.cycle_report.real_target_close_triggered is False
    assert report.cycle_report.target_close_order_sent is False
    assert report.cycle_report.fill_to_first_target_check_seconds == pytest.approx(5.58327)
    assert report.affected_cycles[0].db_id == 25


def test_close_watcher_gap_uses_instrumented_raw_payload(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened = datetime(2026, 7, 20, 18, 20, 16)
    _real_cycle(database, opened_at=opened)
    _order_event(database, timestamp=opened, run_id="run-25", side="BUY", status="FILLED")
    raw = {
        "close_watcher_started_at": (opened + timedelta(seconds=2)).isoformat(),
        "target_check_at": (opened + timedelta(seconds=2, milliseconds=50)).isoformat(),
        "iteration": 1,
        "seconds_since_entry_fill": 2.05,
        "target_condition_result": False,
    }
    _snapshot(
        database,
        cycle_id=25,
        timestamp=opened + timedelta(seconds=2, milliseconds=50),
        phase="tracking",
        price=1.000670,
        bid=1.000670,
        ask=1.000680,
        source="real_pilot_close_watch",
        raw_payload=raw,
    )

    report = HFRealCloseWatcherGapDiagnosticsEngine(database).build_report(PROFILE, real_cycle_id=25)

    assert report.cycle_report is not None
    assert report.cycle_report.close_watcher_started_at == raw["close_watcher_started_at"]
    assert report.cycle_report.target_checks[0].iteration == 1
    assert report.cycle_report.target_checks[0].seconds_from_entry_fill == pytest.approx(2.05)


def test_close_watcher_gap_counts_immediate_target_triggers(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened = datetime(2026, 7, 20, 18, 20, 16)
    closed = opened + timedelta(seconds=1)
    _real_cycle(database, opened_at=opened, closed_at=closed)
    with database.connect() as conn:
        conn.execute(
            "UPDATE real_pilot_cycles SET close_reason = 'real_pilot_target', close_price = 1.00069, net_profit = 0.00005 WHERE id = 25",
        )
        conn.commit()
    _order_event(database, timestamp=opened, run_id="run-25", side="BUY", status="FILLED")
    raw = {
        "close_trigger_source": "immediate_post_fill",
        "immediate_target_check_at": (opened + timedelta(milliseconds=20)).isoformat(),
        "target_check_at": (opened + timedelta(milliseconds=20)).isoformat(),
        "iteration": 0,
        "seconds_since_entry_fill": 0.02,
        "immediate_target_condition_result": True,
        "target_condition_result": True,
    }
    _snapshot(
        database,
        cycle_id=25,
        timestamp=opened + timedelta(milliseconds=20),
        phase="exit",
        price=1.00069,
        bid=1.00069,
        ask=1.00070,
        source="real_pilot_close_watch",
        raw_payload=raw,
    )
    _order_event(
        database,
        timestamp=opened + timedelta(milliseconds=30),
        run_id="close-25",
        side="SELL",
        status="ATTEMPTED_CLOSE",
        close_cycle_id=25,
        close_reason="real_pilot_target",
    )
    _order_event(
        database,
        timestamp=opened + timedelta(milliseconds=40),
        run_id="close-25",
        side="SELL",
        status="FILLED",
        close_cycle_id=25,
        close_reason="real_pilot_target",
    )

    report = HFRealCloseWatcherGapDiagnosticsEngine(database).build_report(PROFILE, real_cycle_id=25)

    assert report.immediate_checks_performed == 1
    assert report.immediate_target_triggers == 1
    assert report.regular_watcher_triggers == 0
    assert report.missed_executable_touches == 0
    assert report.cycle_report.target_checks[0].close_trigger_source == "immediate_post_fill"


def test_close_watcher_gap_handles_db26_immediate_mixed_timezone_timestamps(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened = datetime(2026, 7, 20, 19, 0, 0)
    filled = opened - timedelta(milliseconds=20)
    _real_cycle(
        database,
        db_id=26,
        opened_at=opened,
        closed_at=opened + timedelta(seconds=271),
    )
    _order_event(database, timestamp=filled, run_id="run-25", side="BUY", status="FILLED")
    immediate_at = datetime(2026, 7, 20, 19, 0, 0, 30_000, tzinfo=timezone.utc)
    immediate_raw = {
        "close_trigger_source": "immediate_post_fill",
        "close_watcher_started_at": immediate_at.isoformat(),
        "immediate_target_check_at": immediate_at.isoformat(),
        "target_check_at": immediate_at.isoformat(),
        "iteration": 0,
        "seconds_since_entry_fill": 0.05,
        "immediate_target_check_bid": "1.00067000",
        "immediate_target_check_ask": "1.00068000",
        "immediate_target_check_price": "1.00067000",
        "immediate_target_condition_result": False,
        "target_condition_result": False,
    }
    _snapshot(
        database,
        cycle_id=26,
        timestamp=immediate_at,
        phase="tracking",
        price=1.000670,
        bid=1.000670,
        ask=1.000680,
        source="real_pilot_close_watch",
        raw_payload=immediate_raw,
    )
    regular_at = datetime(2026, 7, 20, 21, 0, 1, tzinfo=timezone(timedelta(hours=2)))
    regular_raw = {
        "close_trigger_source": "regular_watcher",
        "target_check_at": regular_at.isoformat(),
        "iteration": 1,
        "target_condition_result": False,
    }
    _snapshot(
        database,
        cycle_id=26,
        timestamp=regular_at,
        phase="tracking",
        price=1.000665,
        bid=1.000665,
        ask=1.000675,
        source="real_pilot_close_watch",
        raw_payload=regular_raw,
    )
    _order_event(
        database,
        timestamp=opened + timedelta(seconds=270),
        run_id="close-26",
        side="SELL",
        status="ATTEMPTED_CLOSE",
        close_cycle_id=26,
        close_reason="max_holding_270s",
    )
    _order_event(
        database,
        timestamp=opened + timedelta(seconds=271),
        run_id="close-26",
        side="SELL",
        status="FILLED",
        close_cycle_id=26,
        close_reason="max_holding_270s",
    )

    report = HFRealCloseWatcherGapDiagnosticsEngine(database).build_report(PROFILE, real_cycle_id=26)

    assert report.cycles_analyzed == 1
    assert report.immediate_checks_performed == 1
    assert report.immediate_target_triggers == 0
    assert report.missed_executable_touches == 0
    assert report.cycle_report is not None
    assert report.cycle_report.fill_to_first_target_check_seconds == pytest.approx(0.05)
    assert report.cycle_report.target_checks[0].close_trigger_source == "immediate_post_fill"
    assert report.cycle_report.target_checks[0].condition_met is False
    assert report.cycle_report.real_target_close_triggered is False
    assert report.cycle_report.timeout_order_sent_at is not None
    timeline_seconds = [
        event.seconds_from_entry_fill
        for event in report.cycle_report.timeline
        if event.timestamp is not None
    ]
    assert timeline_seconds == sorted(timeline_seconds)
