from datetime import datetime, timedelta

from analytics.session_filter_sim_engine import SessionFilterSimulationEngine
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


def test_session_filter_sim_blocks_bad_and_current_open_cycles(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_v2_small_target"
    asia_opened = datetime(2026, 6, 14, 2, 0, 0)
    london_opened = datetime(2026, 6, 14, 9, 0, 0)
    new_york_opened = datetime(2026, 6, 14, 18, 0, 0)
    _insert_cycle(
        database,
        profile=profile,
        direction="BUY_USDC",
        status="CLOSED_MANUAL",
        open_price=1.0,
        close_price=0.9998,
        quantity=10.0,
        net_profit=-0.002,
        opened_at=asia_opened,
        closed_at=asia_opened + timedelta(minutes=30),
    )
    _insert_cycle(
        database,
        profile=profile,
        direction="SELL_USDC",
        status="OPEN",
        open_price=1.0005,
        close_price=1.0003,
        quantity=10.0,
        net_profit=0.0,
        opened_at=london_opened,
        closed_at=None,
    )
    _insert_cycle(
        database,
        profile=profile,
        direction="SELL_USDC",
        status="CLOSED",
        open_price=1.0005,
        close_price=1.0003,
        quantity=10.0,
        net_profit=0.002,
        opened_at=new_york_opened,
        closed_at=new_york_opened + timedelta(minutes=10),
    )

    report = SessionFilterSimulationEngine(database, test_config).build_report(
        profile=profile,
        current_price=1.0004,
        current_price_source="TEST",
        current_price_timestamp=datetime(2026, 6, 14, 19, 0, 0).isoformat(),
    )

    results = {item.scenario: item for item in report.results}
    assert results["all_sessions"].entries == 3
    assert results["all_sessions"].current_open_cycle_blocked is False
    assert results["exclude_asia"].entries == 2
    assert results["exclude_asia"].historical_bad_cycles_blocked is True
    assert results["exclude_london"].entries == 2
    assert results["exclude_london"].current_open_cycle_blocked is True
    assert results["new_york_only"].entries == 1
    assert results["new_york_only"].win_rate == 1.0
