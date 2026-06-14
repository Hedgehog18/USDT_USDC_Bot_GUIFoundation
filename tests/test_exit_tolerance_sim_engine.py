from datetime import datetime

from analytics.exit_tolerance_sim_engine import ExitToleranceSimulationEngine
from storage.database_manager import DatabaseManager


def _insert_paper_cycle(
    database: DatabaseManager,
    *,
    profile: str,
    direction: str,
    status: str,
    open_price: float,
    close_price: float,
    quantity: float,
    opened_at: datetime,
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
                0.0,
                0.0,
                opened_at.isoformat(),
                opened_at.isoformat() if status == "CLOSED" else None,
            ),
        )
        conn.commit()


def test_exit_tolerance_sim_detects_near_target_close(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    now = datetime.now()
    _insert_paper_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        close_price=1.00020,
        quantity=10.0,
        opened_at=now,
    )
    _insert_paper_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="SELL_USDC",
        status="CLOSED",
        open_price=1.0005,
        close_price=1.0003,
        quantity=10.0,
        opened_at=now,
    )

    report = ExitToleranceSimulationEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=1.00019,
        current_price_source="TEST",
        current_price_timestamp=now.isoformat(),
    )

    strict = next(item for item in report.results if item.tolerance_name == "0_ticks")
    one_tick = next(item for item in report.results if item.tolerance_name == "1_tick")

    assert report.open_cycles_count == 1
    assert report.existing_closed_cycles_count == 1
    assert strict.would_close_now == 0
    assert strict.open_cycles_remaining == 1
    assert one_tick.would_close_now == 1
    assert one_tick.affected_cycles == 1
    assert one_tick.closed_cycles_count == 2
    assert one_tick.open_cycles_remaining == 0
    assert report.open_cycle_details[0].matching_tolerances[0] == "1_tick"
