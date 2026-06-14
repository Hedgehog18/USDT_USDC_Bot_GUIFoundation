from datetime import datetime, timedelta

from analytics.market_session_diagnostics_engine import MarketSessionDiagnosticsEngine
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


def test_market_session_diagnostics_groups_cycles_by_entry_hour(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_v2_small_target"
    asia_opened = datetime(2026, 6, 14, 2, 0, 0)
    overlap_opened = datetime(2026, 6, 14, 14, 0, 0)
    new_york_opened = datetime(2026, 6, 14, 18, 0, 0)
    _insert_cycle(
        database,
        profile=profile,
        direction="BUY_USDC",
        status="CLOSED",
        open_price=1.0,
        close_price=1.0002,
        quantity=10.0,
        net_profit=0.002,
        opened_at=asia_opened,
        closed_at=asia_opened + timedelta(minutes=5),
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
        opened_at=overlap_opened,
        closed_at=None,
    )
    _insert_cycle(
        database,
        profile=profile,
        direction="SELL_USDC",
        status="CLOSED_MANUAL",
        open_price=1.0005,
        close_price=1.0007,
        quantity=10.0,
        net_profit=-0.002,
        opened_at=new_york_opened,
        closed_at=new_york_opened + timedelta(minutes=10),
    )
    _insert_cycle(
        database,
        profile="other_profile",
        direction="BUY_USDC",
        status="CLOSED",
        open_price=1.0,
        close_price=1.0002,
        quantity=10.0,
        net_profit=0.002,
        opened_at=datetime(2026, 6, 14, 9, 0, 0),
        closed_at=datetime(2026, 6, 14, 9, 5, 0),
    )

    report = MarketSessionDiagnosticsEngine(database, test_config).build_report(
        profile=profile,
        current_price=1.0004,
        current_price_source="TEST",
        current_price_timestamp=datetime(2026, 6, 14, 19, 0, 0).isoformat(),
    )

    sessions = {item.session: item for item in report.session_stats}
    assert sessions["ASIA"].total_entries == 1
    assert sessions["ASIA"].closed_cycles == 1
    assert sessions["ASIA"].win_rate == 1.0
    assert sessions["ASIA"].target_hit_rate == 1.0
    assert sessions["LONDON_NEW_YORK_OVERLAP"].total_entries == 1
    assert sessions["LONDON_NEW_YORK_OVERLAP"].open_cycles == 1
    assert sessions["LONDON_NEW_YORK_OVERLAP"].average_unrealized_pnl is not None
    assert sessions["NEW_YORK"].closed_cycles == 1
    assert sessions["NEW_YORK"].win_rate == 0.0
    assert sessions["NEW_YORK"].target_hit_rate == 0.0
    assert report.entry_hour_distribution[2] == 1
    assert report.entry_hour_distribution[14] == 1
    assert report.entry_hour_distribution[18] == 1
    assert report.close_hour_distribution[2] == 1
    assert report.close_hour_distribution[18] == 1
