from datetime import datetime, timedelta

from analytics.exit_rule_sim_engine import ExitRuleSimulationEngine
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
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opened_at.isoformat(),
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
                center_confidence, center_alignment,
                market_activity_score, market_regime
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


def test_exit_rule_sim_no_exit_keeps_open_exposure(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    now = datetime.now()
    _insert_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="SELL_USDC",
        status="CLOSED",
        open_price=1.001,
        close_price=1.0008,
        quantity=10.0,
        net_profit=0.002,
        opened_at=now - timedelta(hours=2),
        closed_at=now - timedelta(hours=1),
    )
    _insert_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        close_price=1.00005,
        quantity=10.0,
        net_profit=0.0,
        opened_at=now - timedelta(hours=3),
        closed_at=None,
    )

    report = ExitRuleSimulationEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=0.9999,
        current_price_timestamp=now.isoformat(),
    )

    no_exit = next(item for item in report.results if item.rule_name == "no_exit_rule")
    assert no_exit.closed_target_profit > 0.0
    assert no_exit.open_exposure_count == 1
    assert no_exit.simulated_stop_timeout_losses == 0.0


def test_exit_rule_sim_stop_loss_can_preempt_target_close(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    now = datetime.now()
    opened_at = now - timedelta(hours=3)
    closed_at = now - timedelta(hours=1)
    _insert_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="BUY_USDC",
        status="CLOSED",
        open_price=1.0,
        close_price=1.00005,
        quantity=10.0,
        net_profit=0.001,
        opened_at=opened_at,
        closed_at=closed_at,
    )
    _insert_snapshot(database, opened_at + timedelta(minutes=30), 0.9996)

    report = ExitRuleSimulationEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=1.0,
        current_price_timestamp=now.isoformat(),
    )

    no_exit = next(item for item in report.results if item.rule_name == "no_exit_rule")
    stop = next(item for item in report.results if item.rule_name == "stop_loss_0_03_percent")

    assert no_exit.closed_target_profit > 0.0
    assert stop.closed_target_profit == 0.0
    assert stop.simulated_stop_timeout_losses < 0.0
    assert stop.max_loss is not None
    assert stop.max_loss < 0.0
