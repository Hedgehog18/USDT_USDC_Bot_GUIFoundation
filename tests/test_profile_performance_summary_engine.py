from datetime import datetime, timedelta

import pytest

from analytics.profile_performance_summary_engine import ProfilePerformanceSummaryEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    profile: str,
    direction: str,
    status: str,
    net_profit: float,
    opened_at: datetime,
    closed_at: datetime | None,
    close_reason: str | None = None,
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (closed_at or opened_at).isoformat(),
                1,
                profile,
                direction,
                status,
                1.0,
                1.0001,
                10.0,
                0.0,
                0.0,
                net_profit,
                net_profit,
                opened_at.isoformat(),
                closed_at.isoformat() if closed_at else None,
                close_reason,
            ),
        )
        conn.commit()


def test_profile_performance_summary_accounts_for_manual_closes(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_v2_small_target"
    start = datetime(2026, 6, 26, 14, 0, 0)
    for index in range(50):
        opened_at = start + timedelta(minutes=index)
        _insert_cycle(
            database,
            profile=profile,
            direction="BUY_USDC" if index % 2 == 0 else "SELL_USDC",
            status="CLOSED",
            net_profit=0.01,
            opened_at=opened_at,
            closed_at=opened_at + timedelta(minutes=5),
        )
    _insert_cycle(
        database,
        profile=profile,
        direction="BUY_USDC",
        status="CLOSED_MANUAL",
        net_profit=-0.05,
        opened_at=start + timedelta(hours=2),
        closed_at=start + timedelta(hours=3),
        close_reason="stale",
    )
    _insert_cycle(
        database,
        profile=profile,
        direction="SELL_USDC",
        status="OPEN",
        net_profit=0.0,
        opened_at=start + timedelta(hours=4),
        closed_at=None,
    )
    _insert_cycle(
        database,
        profile="other_profile",
        direction="BUY_USDC",
        status="CLOSED_MANUAL",
        net_profit=-1.0,
        opened_at=start,
        closed_at=start + timedelta(minutes=1),
        close_reason="stale",
    )

    summary = ProfilePerformanceSummaryEngine(database).build_summary(profile)

    assert summary.total_profile_cycles == 52
    assert summary.automatic_closed_count == 50
    assert summary.manual_closed_count == 1
    assert summary.open_count == 1
    assert summary.automatic_closed_net_profit == pytest.approx(0.5)
    assert summary.manual_closed_net_profit == pytest.approx(-0.05)
    assert summary.total_realized_net_profit == pytest.approx(0.45)
    assert summary.target_hit_win_rate == 1.0
    assert summary.real_outcome_win_rate == pytest.approx(50 / 51)
    assert summary.stale_close_count == 1
    assert summary.manual_close_rate == pytest.approx(1 / 51)
    assert summary.best_cycle is not None
    assert summary.best_cycle.net_profit == 0.01
    assert summary.worst_cycle is not None
    assert summary.worst_cycle.status == "CLOSED_MANUAL"
    assert summary.average_holding_time_automatic_seconds == 300.0
    assert summary.average_holding_time_manual_seconds == 3600.0
    assert summary.buy_breakdown.total_cycles == 26
    assert summary.sell_breakdown.total_cycles == 26
    assert summary.recommendation == "NEEDS_EXIT_RULE"
