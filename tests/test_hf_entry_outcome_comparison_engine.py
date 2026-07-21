from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from analytics.hf_entry_outcome_comparison_engine import (
    OUTCOME_EXECUTABLE_TARGET_TOUCH,
    OUTCOME_HISTORICAL_ANOMALY,
    OUTCOME_TIMEOUT_NO_TOUCH,
    HFEntryOutcomeComparisonEngine,
    report_to_json,
)
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    direction: str = "BUY_USDC",
    open_price: str = "1.00000000",
    close_price: str = "1.00000500",
    net_profit: str = "0.00005000",
    close_reason: str = "real_pilot_target",
    opened_at: datetime | None = None,
    run_id: str | None = None,
) -> None:
    opened_at = opened_at or datetime(2026, 7, 21, 12, 0, 0)
    closed_at = opened_at + timedelta(seconds=30 if close_reason == "real_pilot_target" else 270)
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_cycles (
                id, timestamp, strategy_profile, symbol, direction, status,
                open_price, close_price, quantity, stake_usdt, gross_profit,
                net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
            ) VALUES (?, ?, ?, 'USDCUSDT', ?, 'CLOSED', ?, ?, 5, 6, ?, ?, ?, ?, ?, 'order-1', ?)
            """,
            (
                db_id,
                opened_at.isoformat(),
                PROFILE,
                direction,
                float(open_price),
                float(close_price),
                float(net_profit),
                float(net_profit),
                opened_at.isoformat(),
                closed_at.isoformat(),
                close_reason,
                run_id or f"run-{db_id}",
            ),
        )
        conn.commit()


def _snapshot(
    database: DatabaseManager,
    *,
    cycle_id: int,
    timestamp: datetime,
    price: str,
    direction: str = "BUY_USDC",
    phase: str = "tracking",
    bid: str | None = None,
    ask: str | None = None,
    short_center: str = "1.00000000",
    spread: str = "0.00001000",
) -> None:
    bid_value = Decimal(bid) if bid is not None else Decimal(price) - Decimal(spread) / Decimal("2")
    ask_value = Decimal(ask) if ask is not None else Decimal(price) + Decimal(spread) / Decimal("2")
    database.save_real_pilot_market_snapshot(
        real_cycle_id=cycle_id,
        campaign_id="campaign-1",
        timestamp=timestamp.isoformat(),
        phase=phase,
        symbol="USDCUSDT",
        price=float(Decimal(price)),
        bid=float(bid_value),
        ask=float(ask_value),
        mid=float(Decimal(price)),
        spread=float(Decimal(spread)),
        short_center=float(Decimal(short_center)),
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction=direction,
        target_price=None,
        distance_to_target=None,
        unrealized_pnl=0.0,
        open_real_cycles=1,
        source="TEST",
    )


def _post_exit_summary(database: DatabaseManager, *, cycle_id: int, touched: bool, seconds: str | None = None) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_post_exit_observer_summaries (
                real_cycle_id, campaign_id, started_at, finished_at, duration_seconds,
                interval_seconds, snapshots_count, post_exit_mfe, post_exit_mae,
                max_price, min_price, post_exit_target_touched, time_to_post_target,
                closest_distance_after_exit, status
            ) VALUES (?, 'campaign-1', '2026-07-21T12:05:00', '2026-07-21T12:10:00',
                      300, 5, 60, 0.000005, -0.000010, 1.000010, 0.999990,
                      ?, ?, 0.000000, 'COMPLETED')
            """,
            (cycle_id, int(touched), None if seconds is None else float(Decimal(seconds))),
        )
        conn.commit()


def _target_touch_cycle(database: DatabaseManager, db_id: int = 1, *, direction: str = "BUY_USDC", opened_at: datetime | None = None) -> None:
    opened_at = opened_at or datetime(2026, 7, 21, 12, 0, 0)
    if direction == "BUY_USDC":
        _cycle(database, db_id=db_id, direction=direction, opened_at=opened_at)
        _snapshot(database, cycle_id=db_id, timestamp=opened_at, price="1.00000000", direction=direction, phase="entry")
        _snapshot(database, cycle_id=db_id, timestamp=opened_at + timedelta(seconds=5), price="1.00000600", bid="1.00000500", ask="1.00000700", direction=direction)
    else:
        _cycle(database, db_id=db_id, direction=direction, open_price="1.00000000", close_price="0.99999500", opened_at=opened_at)
        _snapshot(database, cycle_id=db_id, timestamp=opened_at, price="1.00000000", direction=direction, phase="entry")
        _snapshot(database, cycle_id=db_id, timestamp=opened_at + timedelta(seconds=5), price="0.99999400", bid="0.99999300", ask="0.99999500", direction=direction)


def _timeout_no_touch_cycle(database: DatabaseManager, db_id: int = 2, *, direction: str = "BUY_USDC", opened_at: datetime | None = None) -> None:
    opened_at = opened_at or datetime(2026, 7, 21, 12, 10, 0)
    if direction == "BUY_USDC":
        _cycle(database, db_id=db_id, direction=direction, close_price="0.99999000", net_profit="-0.00005000", close_reason="max_holding_270s", opened_at=opened_at)
        _snapshot(database, cycle_id=db_id, timestamp=opened_at, price="1.00000000", direction=direction, phase="entry")
        _snapshot(database, cycle_id=db_id, timestamp=opened_at + timedelta(seconds=5), price="0.99999000", bid="0.99998500", ask="0.99999500", direction=direction)
    else:
        _cycle(database, db_id=db_id, direction=direction, open_price="1.00000000", close_price="1.00001000", net_profit="-0.00005000", close_reason="max_holding_270s", opened_at=opened_at)
        _snapshot(database, cycle_id=db_id, timestamp=opened_at, price="1.00000000", direction=direction, phase="entry")
        _snapshot(database, cycle_id=db_id, timestamp=opened_at + timedelta(seconds=5), price="1.00001000", bid="1.00000500", ask="1.00001500", direction=direction)


def test_entry_outcome_comparison_splits_target_touch_and_timeout_no_touch(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _target_touch_cycle(database, 1)
    _timeout_no_touch_cycle(database, 2)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert report.target_touch_group.sample_size == 1
    assert report.timeout_no_touch_group.sample_size == 1
    assert report.cycle_table[0].outcome_group == OUTCOME_EXECUTABLE_TARGET_TOUCH
    assert report.cycle_table[1].outcome_group == OUTCOME_TIMEOUT_NO_TOUCH


def test_entry_outcome_comparison_excludes_cycles_without_blackbox(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _cycle(database, db_id=1)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert report.cycles_without_blackbox == 1
    assert report.cycles_analyzed == 0


def test_entry_outcome_comparison_handles_db25_as_historical_anomaly(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _timeout_no_touch_cycle(database, db_id=25)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert report.cycles_analyzed == 0
    assert len(report.historical_anomalies) == 1
    assert report.historical_anomalies[0].db_id == 25
    assert report.historical_anomalies[0].outcome_group == OUTCOME_HISTORICAL_ANOMALY


def test_entry_outcome_comparison_buy_sell_breakdown(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _target_touch_cycle(database, 1, direction="BUY_USDC")
    _target_touch_cycle(database, 2, direction="SELL_USDC")
    _timeout_no_touch_cycle(database, 3, direction="BUY_USDC")
    _timeout_no_touch_cycle(database, 4, direction="SELL_USDC")

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert report.target_touch_group.buy_count == 1
    assert report.target_touch_group.sell_count == 1
    assert report.timeout_no_touch_group.buy_count == 1
    assert report.timeout_no_touch_group.sell_count == 1
    assert report.direction_group_stats[OUTCOME_TIMEOUT_NO_TOUCH]["SELL_USDC"].sample_size == 1


def test_entry_outcome_comparison_uses_decimal_and_median(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 21, 12, 0, 0)
    _target_touch_cycle(database, 1, opened_at=start)
    _target_touch_cycle(database, 2, opened_at=start + timedelta(minutes=1))
    _target_touch_cycle(database, 3, opened_at=start + timedelta(minutes=2))

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert isinstance(report.target_touch_group.average_spread, Decimal)
    assert report.target_touch_group.median_spread == Decimal("0.00001")
    assert report.target_touch_group.sample_size == 3


def test_entry_outcome_comparison_early_movement_direction(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _target_touch_cycle(database, 1)
    _timeout_no_touch_cycle(database, 2)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    target_5s = next(bucket for bucket in report.early_movement if bucket.group_name == OUTCOME_EXECUTABLE_TARGET_TOUCH and bucket.interval_seconds == 5)
    timeout_5s = next(bucket for bucket in report.early_movement if bucket.group_name == OUTCOME_TIMEOUT_NO_TOUCH and bucket.interval_seconds == 5)
    assert target_5s.toward_target == 1
    assert timeout_5s.against_target == 1


def test_entry_outcome_comparison_repeated_entry_clusters(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 21, 12, 0, 0)
    _target_touch_cycle(database, 1, opened_at=start)
    _timeout_no_touch_cycle(database, 2, opened_at=start + timedelta(minutes=3))

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert len(report.repeated_entry_clusters) == 1
    cluster = report.repeated_entry_clusters[0]
    assert cluster.cycle_ids == [1, 2]
    assert cluster.repeated_timeout_rate == Decimal("1")


def test_entry_outcome_comparison_low_sample_size_warning(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _target_touch_cycle(database, 1)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert any(warning.startswith("LOW_SAMPLE_SIZE") for warning in report.warnings)
    assert report.recommendation == "CONTINUE_COLLECTING"


def test_entry_outcome_comparison_post_exit_timeout_stats(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _timeout_no_touch_cycle(database, 1, direction="BUY_USDC")
    _timeout_no_touch_cycle(database, 2, direction="SELL_USDC")
    _post_exit_summary(database, cycle_id=1, touched=True, seconds="45")
    _post_exit_summary(database, cycle_id=2, touched=False)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    assert report.post_exit_outcomes.timeout_cycles_with_observer == 2
    assert report.post_exit_outcomes.target_reached_after_timeout == 1
    assert report.post_exit_outcomes.never_reached_after_timeout == 1
    assert report.post_exit_outcomes.average_time_to_post_target == Decimal("45.0")
    assert report.post_exit_outcomes.buy_target_reached_after_timeout == 1


def test_entry_outcome_comparison_json_output(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _target_touch_cycle(database, 1)

    report = HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)
    payload = report_to_json(report)

    assert '"profile": "mean_reversion_hf_micro_v1"' in payload
    assert '"recommendation": "CONTINUE_COLLECTING"' in payload


def test_entry_outcome_comparison_does_not_create_orders_or_call_api(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _target_touch_cycle(database, 1)

    HFEntryOutcomeComparisonEngine(database).build_report(PROFILE)

    with database.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM real_pilot_order_events").fetchone()[0]
    assert count == 0
