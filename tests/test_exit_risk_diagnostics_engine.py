from datetime import datetime, timedelta

from analytics.exit_risk_diagnostics_engine import ExitRiskDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    profile: str,
    direction: str,
    status: str,
    open_price: float,
    close_price: float,
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
                10.0,
                0.0,
                0.0,
                net_profit,
                net_profit,
                opened_at.isoformat(),
                closed_at.isoformat() if closed_at else None,
            ),
        )
        conn.commit()


def test_exit_risk_diagnostics_builds_open_cycle_stop_report(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime.now() - timedelta(hours=5)
    _insert_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        close_price=1.00005,
        net_profit=0.0,
        opened_at=opened_at,
        closed_at=None,
    )

    report = ExitRiskDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=0.9998,
        current_price_source="TEST",
        current_price_timestamp="2026-01-01T00:00:00",
    )

    assert report.profile == "mean_reversion_v2_small_target"
    assert len(report.open_cycles) == 1
    item = report.open_cycles[0]
    assert item.direction == "BUY_USDC"
    assert item.unrealized_pnl < 0.0
    assert item.adverse_move_percent > 0.01
    assert item.would_stop_at[0.005] is True
    assert report.historical_summary.open_unrealized_pnl < 0.0
    assert any(result.max_age_seconds == 4 * 60 * 60 and result.would_timeout_count == 1 for result in report.max_holding_results)
    assert "stop" in report.recommendation


def test_exit_risk_diagnostics_combines_closed_and_open_pnl(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    now = datetime.now()
    _insert_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="SELL_USDC",
        status="CLOSED",
        open_price=1.001,
        close_price=1.0008,
        net_profit=0.002,
        opened_at=now - timedelta(minutes=10),
        closed_at=now,
    )
    _insert_cycle(
        database,
        profile="mean_reversion_v2_small_target",
        direction="BUY_USDC",
        status="OPEN",
        open_price=1.0,
        close_price=1.00005,
        net_profit=0.0,
        opened_at=now - timedelta(minutes=5),
        closed_at=None,
    )

    report = ExitRiskDiagnosticsEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=1.00002,
    )

    assert report.historical_summary.closed_net_profit == 0.002
    assert report.historical_summary.open_unrealized_pnl > 0.0
    assert report.historical_summary.combined_realized_unrealized_pnl > 0.002
    assert report.historical_summary.best_closed_profit == 0.002
    assert report.historical_summary.avg_holding_time_closed_seconds == 600.0
