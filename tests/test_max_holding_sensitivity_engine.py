from datetime import datetime, timedelta

from analytics.max_holding_sensitivity_engine import MaxHoldingSensitivityEngine
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


def test_max_holding_sensitivity_counts_target_and_timeout_closes(test_config, tmp_path):
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
        opened_at=now - timedelta(minutes=20),
        closed_at=now - timedelta(minutes=10),
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
        opened_at=now - timedelta(hours=2),
        closed_at=None,
    )

    report = MaxHoldingSensitivityEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=0.9998,
        thresholds=(30 * 60,),
    )

    result = report.results[0]
    assert report.total_cycles == 2
    assert result.cycles_affected == 2
    assert result.realized_target_closes == 1
    assert result.would_close_by_timeout == 1
    assert result.timeout_close_estimated_pnl < 0.0
    assert result.combined_pnl < 0.002
    assert result.win_rate_including_timeouts == 0.5
    assert result.worst_timeout_loss is not None
    assert report.recommended_max_age_seconds == 30 * 60


def test_max_holding_sensitivity_uses_snapshot_price_at_timeout(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime.now() - timedelta(hours=3)
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
        closed_at=opened_at + timedelta(hours=2),
    )
    _insert_snapshot(database, opened_at + timedelta(hours=1, minutes=1), 0.9999)

    report = MaxHoldingSensitivityEngine(database, test_config).build_report(
        profile="mean_reversion_v2_small_target",
        current_price=1.0,
        thresholds=(60 * 60,),
    )

    result = report.results[0]
    assert result.realized_target_closes == 0
    assert result.would_close_by_timeout == 1
    assert result.timeout_close_estimated_pnl < 0.0
