from datetime import datetime, timedelta

import pytest

from analytics.exit_rule_optimizer_engine import ExitRuleOptimizerEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    profile: str,
    direction: str,
    status: str,
    open_price: float,
    close_price: float,
    quantity: float,
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
                open_price,
                close_price,
                quantity,
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


def _insert_snapshot(database: DatabaseManager, timestamp: datetime, price: float) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO market_snapshots (
                timestamp, symbol, price, bid, ask, spread,
                work_center, work_position,
                short_center, short_position,
                long_center, long_position,
                center_confidence, center_alignment, market_activity_score,
                market_regime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                "USDCUSDT",
                price,
                price - 0.00001,
                price + 0.00001,
                0.00002,
                1.0,
                50.0,
                1.0,
                50.0,
                1.0,
                50.0,
                "HIGH",
                "ALIGNED",
                80.0,
                "NORMAL",
            ),
        )
        conn.commit()


def test_exit_rule_optimizer_can_avoid_manual_stale_cycle(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_v2_small_target"
    opened_at = datetime(2026, 6, 26, 8, 0, 0)
    manual_closed_at = opened_at + timedelta(hours=30)
    _insert_cycle(
        database,
        profile=profile,
        direction="BUY_USDC",
        status="CLOSED_MANUAL",
        open_price=1.0,
        close_price=0.999,
        quantity=10.0,
        net_profit=-0.01,
        opened_at=opened_at,
        closed_at=manual_closed_at,
        close_reason="stale",
    )
    _insert_cycle(
        database,
        profile=profile,
        direction="SELL_USDC",
        status="CLOSED",
        open_price=1.0,
        close_price=0.9999,
        quantity=10.0,
        net_profit=0.001,
        opened_at=opened_at + timedelta(minutes=5),
        closed_at=opened_at + timedelta(minutes=20),
    )
    _insert_cycle(
        database,
        profile="other_profile",
        direction="BUY_USDC",
        status="CLOSED_MANUAL",
        open_price=1.0,
        close_price=0.5,
        quantity=10.0,
        net_profit=-5.0,
        opened_at=opened_at,
        closed_at=manual_closed_at,
        close_reason="stale",
    )
    _insert_snapshot(database, opened_at + timedelta(hours=8), 0.9998)

    report = ExitRuleOptimizerEngine(database, test_config).build_report(
        profile=profile,
        current_price=0.9997,
        current_price_source="TEST",
        current_price_timestamp=(opened_at + timedelta(hours=31)).isoformat(),
    )

    by_name = {item.scenario: item for item in report.scenarios}
    assert report.total_cycles == 2
    assert by_name["no_exit_rule"].manual_stale_cycles_avoided == 0
    assert by_name["no_exit_rule"].forced_exits_count == 0
    assert by_name["no_exit_rule"].simulated_total_net == pytest.approx(-0.009)
    assert by_name["max_holding_8h"].manual_stale_cycles_avoided == 1
    assert by_name["max_holding_8h"].forced_exits_count == 1
    assert by_name["max_holding_8h"].forced_exits_net > -0.01
    assert by_name["max_holding_8h"].automatic_target_closes == 1
    assert report.recommended_scenario is not None
