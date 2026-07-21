from datetime import datetime, timedelta

import pytest

from analytics.hf_real_entry_quality_engine import HFRealEntryQualityDiagnosticsEngine
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _real_cycle(
    database: DatabaseManager,
    *,
    db_id: int = 1,
    direction: str = "BUY_USDC",
    open_price: float = 1.0,
    close_price: float = 1.000005,
    quantity: float = 10.0,
    net_profit: float = 0.00005,
    close_reason: str = "real_pilot_target",
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
    run_id: str = "run-1",
) -> None:
    opened_at = opened_at or datetime(2026, 7, 8, 12, 0, 0)
    closed_at = closed_at or opened_at + timedelta(seconds=60)
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_cycles (
                id, timestamp, strategy_profile, symbol, direction, status,
                open_price, close_price, quantity, stake_usdt, gross_profit,
                net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
            ) VALUES (?, ?, ?, 'USDCUSDT', ?, 'CLOSED', ?, ?, ?, 6, ?, ?, ?, ?, ?, 'entry-order', ?)
            """,
            (
                db_id,
                opened_at.isoformat(),
                PROFILE,
                direction,
                open_price,
                close_price,
                quantity,
                net_profit,
                net_profit,
                opened_at.isoformat(),
                closed_at.isoformat(),
                close_reason,
                run_id,
            ),
        )
        conn.commit()


def _snapshot(
    database: DatabaseManager,
    cycle_id: int,
    timestamp: datetime,
    price: float,
    *,
    phase: str = "tracking",
    direction: str = "BUY_USDC",
    target_price: float = 1.000005,
    short_center: float = 1.00001,
    spread: float = 0.000001,
    candidate: bool = True,
    block_reason: str = "N/A",
) -> None:
    database.save_real_pilot_market_snapshot(
        real_cycle_id=cycle_id,
        campaign_id="campaign-1",
        timestamp=timestamp.isoformat(),
        phase=phase,
        symbol="USDCUSDT",
        price=price,
        bid=price - spread / 2.0,
        ask=price + spread / 2.0,
        mid=price,
        spread=spread,
        short_center=short_center,
        hf_entry_mode="short_center",
        candidate=candidate,
        block_reason=block_reason,
        direction=direction,
        target_price=target_price,
        distance_to_target=target_price - price,
        unrealized_pnl=0.0,
        open_real_cycles=1,
        source="TEST",
    )


def test_entry_quality_handles_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    assert report.total_analyzed_cycles == 0
    assert report.cycles == []
    assert report.main_issue == "no_real_cycles"
    assert report.recommendation == "RUN_MORE_BLACKBOX_SMALL_REAL"


def test_entry_quality_counts_cycles_without_blackbox(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _real_cycle(database)

    report = HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    assert report.total_analyzed_cycles == 1
    assert report.cycles_with_blackbox == 0
    assert report.cycles_without_blackbox == 1
    assert report.main_issue == "insufficient_data"


def test_entry_quality_target_cycle_categorized_as_good_follow_through(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(database, opened_at=start, closed_at=start + timedelta(seconds=15))
    _snapshot(database, 1, start, 1.0, phase="entry")
    _snapshot(database, 1, start + timedelta(seconds=5), 1.000002)
    _snapshot(database, 1, start + timedelta(seconds=15), 1.000006)

    report = HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    cycle = report.cycles[0]
    assert cycle.target_touched is True
    assert cycle.reference_target_touched is True
    assert cycle.executable_target_touched is True
    assert cycle.real_target_close_triggered is True
    assert cycle.entry_quality_category == "good_entry_follow_through"
    assert cycle.movement_after_5s == pytest.approx(0.000002)
    assert report.target_metrics.count == 1
    assert report.target_metrics.target_touch_rate == pytest.approx(1.0)
    assert report.executable_target_touched_count == 1


def test_entry_quality_timeout_no_touch_categorized(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(
        database,
        open_price=1.0,
        close_price=0.99999,
        net_profit=-0.0001,
        close_reason="max_holding_270s",
        opened_at=start,
        closed_at=start + timedelta(seconds=270),
    )
    _snapshot(database, 1, start, 1.0, phase="entry")
    _snapshot(database, 1, start + timedelta(seconds=5), 1.000003)
    _snapshot(database, 1, start + timedelta(seconds=270), 0.99999, phase="exit")

    report = HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    cycle = report.cycles[0]
    assert cycle.target_touched is False
    assert cycle.entry_quality_category == "weak_follow_through"
    assert report.timeout_no_touch_count == 1
    assert report.timeout_loss_count == 1


def test_entry_quality_immediate_adverse_move_categorized(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(
        database,
        open_price=1.0,
        close_price=0.99999,
        net_profit=-0.0001,
        close_reason="max_holding_270s",
        opened_at=start,
    )
    _snapshot(database, 1, start, 1.0, phase="entry")
    _snapshot(database, 1, start + timedelta(seconds=5), 0.99999)

    report = HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    assert report.cycles[0].entry_quality_category == "immediate_adverse_move"


def test_entry_quality_summary_computes_target_vs_timeout_metrics(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(database, db_id=1, opened_at=start)
    _snapshot(database, 1, start, 1.0, phase="entry")
    _snapshot(database, 1, start + timedelta(seconds=10), 1.000006)
    _real_cycle(
        database,
        db_id=2,
        open_price=1.0,
        close_price=1.0,
        net_profit=0.0,
        close_reason="max_holding_270s",
        opened_at=start + timedelta(minutes=10),
        run_id="run-2",
    )
    _snapshot(database, 2, start + timedelta(minutes=10), 1.0, phase="entry")
    _snapshot(database, 2, start + timedelta(minutes=10, seconds=270), 1.0, phase="exit")

    report = HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    assert report.target_metrics.count == 1
    assert report.timeout_metrics.count == 1
    assert report.breakeven_count == 1
    assert report.timeout_metrics.timeout_loss_rate == pytest.approx(0.0)
    assert report.target_touched_count == 1


def test_entry_quality_diagnostics_do_not_create_orders(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(database, opened_at=start)
    _snapshot(database, 1, start, 1.0, phase="entry")

    HFRealEntryQualityDiagnosticsEngine(database).build_report(PROFILE)

    with database.connect() as conn:
        row = conn.execute("SELECT COUNT(*) FROM real_pilot_order_events").fetchone()
    assert row[0] == 0
