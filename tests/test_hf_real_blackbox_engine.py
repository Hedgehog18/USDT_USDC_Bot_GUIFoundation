from datetime import datetime, timedelta

import pytest

from analytics.hf_real_blackbox_engine import (
    HFRealBlackboxDiagnosticsEngine,
    HFRealBlackboxRecorder,
)
from analytics.hf_real_pilot_engine import HFRealPilotSignalSnapshot
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _cycle(database: DatabaseManager, *, status: str = "CLOSED") -> int:
    cycle_id = database.save_real_pilot_cycle(
        run_id="run-1",
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        quantity=10,
        stake_usdt=10,
        exchange_order_id="entry-1",
    )
    if status == "CLOSED":
        database.close_real_pilot_cycle(
            cycle_id,
            close_price=1.000004,
            gross_profit=0.00004,
            net_profit=0.00004,
            close_reason="max_holding_270s",
        )
    return cycle_id


def _save_snapshot(database: DatabaseManager, cycle_id: int, timestamp: datetime, price: float, *, phase: str = "tracking") -> None:
    database.save_real_pilot_market_snapshot(
        real_cycle_id=cycle_id,
        campaign_id="campaign-1",
        timestamp=timestamp.isoformat(),
        phase=phase,
        symbol="USDCUSDT",
        price=price,
        bid=price - 0.000005,
        ask=price + 0.000005,
        mid=price,
        spread=0.00001,
        short_center=1.0,
        hf_entry_mode="test",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.000005,
        distance_to_target=1.000005 - price,
        unrealized_pnl=(price - 1.0) * 10,
        open_real_cycles=1,
        source="TEST",
    )


def test_real_pilot_market_snapshots_table_created(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    with database.connect() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='real_pilot_market_snapshots'"
        ).fetchone()

    assert row is not None


def test_blackbox_recorder_stores_pre_entry_snapshot(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    recorder = HFRealBlackboxRecorder(database, "USDCUSDT")
    signal = HFRealPilotSignalSnapshot(
        price=1.0,
        short_center=1.00001,
        hf_entry_mode="short_center",
        candidate=False,
        entry_signal=None,
        block_reason="no_signal",
        bid=0.999995,
        ask=1.000005,
        spread=0.00001,
        source="TEST",
    )

    snapshot_id = recorder.record_signal_snapshot(phase="pre_entry", signal=signal, campaign_id="campaign-1")

    assert snapshot_id > 0
    with database.connect() as conn:
        row = conn.execute("SELECT phase, price, bid, ask FROM real_pilot_market_snapshots").fetchone()
    assert row == ("pre_entry", 1.0, 0.999995, 1.000005)


def test_blackbox_recorder_attaches_recent_pre_entry_to_real_cycle(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    recorder = HFRealBlackboxRecorder(database, "USDCUSDT")
    signal = HFRealPilotSignalSnapshot(
        price=1.0,
        short_center=1.00001,
        hf_entry_mode="short_center",
        candidate=True,
        entry_signal="BUY_USDC",
        block_reason="N/A",
    )
    recorder.record_signal_snapshot(phase="pre_entry", signal=signal, campaign_id="campaign-1")
    cycle_id = _cycle(database, status="OPEN")

    attached = recorder.attach_recent_pre_entry(real_cycle_id=cycle_id, campaign_id="campaign-1")

    assert attached == 1
    assert database.count_real_pilot_market_snapshots(cycle_id) == 1


def test_blackbox_cli_metrics_calculate_mfe_mae_and_target_touch(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    cycle_id = _cycle(database)
    opened = datetime.fromisoformat(database.load_real_pilot_cycle_by_id(cycle_id)["opened_at"])
    _save_snapshot(database, cycle_id, opened, 1.0, phase="entry")
    _save_snapshot(database, cycle_id, opened + timedelta(seconds=5), 0.99999)
    _save_snapshot(database, cycle_id, opened + timedelta(seconds=10), 1.000006)
    _save_snapshot(database, cycle_id, opened + timedelta(seconds=270), 1.000004, phase="exit")

    report = HFRealBlackboxDiagnosticsEngine(database).build_report(profile=PROFILE, real_cycle_id=cycle_id)

    assert report.metrics is not None
    assert report.metrics.snapshots_count == 4
    assert report.metrics.tracking_count == 2
    assert report.metrics.exit_count == 1
    assert report.metrics.max_favorable_excursion == pytest.approx(0.000006)
    assert report.metrics.max_adverse_excursion == pytest.approx(-0.00001)
    assert report.metrics.target_touched is True
    assert report.metrics.reference_target_touched is True
    assert report.metrics.executable_target_touched is False
    assert report.metrics.real_target_close_triggered is False
    assert report.metrics.first_target_touch_seconds == pytest.approx(10)
    assert report.metrics.first_executable_target_touch_seconds is None
    assert report.metrics.suspected_reason == "reference_touch_only"


def test_blackbox_distinguishes_reference_touch_from_real_target_close_for_db25_shape(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened = datetime(2026, 7, 20, 18, 20, 16)
    closed = opened + timedelta(seconds=270)
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_cycles (
                id, timestamp, strategy_profile, symbol, direction, status,
                open_price, close_price, quantity, stake_usdt, gross_profit,
                net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
            ) VALUES (25, ?, ?, 'USDCUSDT', 'BUY_USDC', 'CLOSED',
                1.00068000, 1.00064000, 5, 6, -0.0002, -0.0002,
                ?, ?, 'max_holding_270s', 'entry-25', 'run-25')
            """,
            (opened.isoformat(), PROFILE, opened.isoformat(), closed.isoformat()),
        )
        conn.commit()
    database.save_real_pilot_market_snapshot(
        real_cycle_id=25,
        campaign_id="campaign-25",
        timestamp=(opened + timedelta(milliseconds=24)).isoformat(),
        phase="entry",
        symbol="USDCUSDT",
        price=1.00069500,
        bid=1.00069000,
        ask=1.00070000,
        mid=1.00069500,
        spread=0.00001,
        short_center=1.00071500,
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.0006850034,
        distance_to_target=None,
        unrealized_pnl=None,
        open_real_cycles=1,
        source="TEST",
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=25,
        campaign_id="campaign-25",
        timestamp=closed.isoformat(),
        phase="exit",
        symbol="USDCUSDT",
        price=1.00064000,
        bid=1.00064000,
        ask=1.00065000,
        mid=1.00064500,
        spread=0.00001,
        short_center=None,
        hf_entry_mode=None,
        candidate=None,
        block_reason=None,
        direction="BUY_USDC",
        target_price=1.0006850034,
        distance_to_target=0.0000450034,
        unrealized_pnl=-0.0002,
        open_real_cycles=1,
        source="TEST",
    )

    report = HFRealBlackboxDiagnosticsEngine(database).build_report(profile=PROFILE, real_cycle_id=25)

    assert report.metrics is not None
    assert report.metrics.reference_target_touched is True
    assert report.metrics.executable_target_touched is True
    assert report.metrics.real_target_close_triggered is False
    assert report.metrics.target_touched is True
    assert report.metrics.first_target_touch_seconds == pytest.approx(0.024)
    assert report.metrics.first_executable_target_touch_seconds == pytest.approx(0.024)
    assert report.metrics.suspected_reason == "target_touched_but_not_executed"


def test_blackbox_cli_handles_missing_cycle_and_no_snapshots(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    missing = HFRealBlackboxDiagnosticsEngine(database).build_report(profile=PROFILE, real_cycle_id=404)
    cycle_id = _cycle(database)
    empty = HFRealBlackboxDiagnosticsEngine(database).build_report(profile=PROFILE, real_cycle_id=cycle_id)

    assert missing.recommendation == "CYCLE_NOT_FOUND"
    assert empty.recommendation == "RUN_NEW_CAMPAIGN_WITH_RECORDER"
    assert empty.metrics is None
