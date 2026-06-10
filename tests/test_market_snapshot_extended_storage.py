from datetime import datetime

from market.models import MarketState
from storage.database_manager import DatabaseManager


def test_database_saves_extended_market_snapshot_metrics(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    state = MarketState(
        symbol="USDCUSDT",
        price=1.0,
        bid=0.99999,
        ask=1.00001,
        spread=0.00002,
        work_low=0.9999,
        work_high=1.0001,
        work_center=1.0,
        work_position=18.0,
        short_low=0.9998,
        short_high=1.0002,
        short_center=1.0,
        short_position=45.0,
        long_low=0.9995,
        long_high=1.0005,
        long_center=1.0,
        long_position=55.0,
        center_confidence="MEDIUM",
        center_alignment="ALIGNED",
        tick_activity_score=11.0,
        center_crossing_score=22.0,
        mean_reversion_score=33.0,
        spread_stability_score=44.0,
        corridor_quality_score=55.0,
        market_activity_score=66.0,
        market_regime="NORMAL",
        order_book_imbalance=0.12,
        order_book_pressure="BID_PRESSURE",
        trade_volume_delta=0.34,
        micro_trend="BUY_DOMINANT",
        relative_volatility=0.00001,
        volatility_regime="LOW",
        market_health_score=99.0,
        market_health_status="HEALTHY",
        market_health_reason="ok",
        created_at=datetime.utcnow(),
    )

    snapshot_id = database.save_market_snapshot(state)

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT
                tick_activity_score,
                center_crossing_score,
                mean_reversion_score,
                spread_stability_score,
                corridor_quality_score,
                order_book_imbalance,
                order_book_pressure,
                micro_trend,
                relative_volatility,
                volatility_regime,
                market_health_score,
                market_health_status,
                market_health_reason
            FROM market_snapshots
            WHERE id = ?
            """,
            (snapshot_id,),
        ).fetchone()

    assert row == (
        11.0,
        22.0,
        33.0,
        44.0,
        55.0,
        0.12,
        "BID_PRESSURE",
        "BUY_DOMINANT",
        0.00001,
        "LOW",
        99.0,
        "HEALTHY",
        "ok",
    )
