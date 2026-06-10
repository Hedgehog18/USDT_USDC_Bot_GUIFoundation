from types import SimpleNamespace

from analytics.filter_pass_diagnostics_engine import FilterPassDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _config():
    return SimpleNamespace(
        buy_zone_max=20.0,
        sell_zone_min=80.0,
        max_allowed_spread=0.0002,
        min_market_health_score=50.0,
    )


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    spread: float = 0.0001,
    center_confidence: str = "HIGH",
    market_regime: str = "NORMAL",
    order_book_pressure: str = "BID_PRESSURE",
    micro_trend: str = "BUY_DOMINANT",
    volatility_regime: str = "NORMAL",
    corridor_quality_score: float = 80.0,
    mean_reversion_score: float = 70.0,
    market_health_score: float = 100.0,
    market_health_status: str = "HEALTHY",
) -> None:
    conn.execute(
        """
        INSERT INTO market_snapshots (
            timestamp, symbol, price, bid, ask, spread,
            work_center, work_position,
            short_center, short_position,
            long_center, long_position,
            center_confidence, center_alignment,
            market_activity_score, market_regime,
            order_book_pressure, micro_trend, volatility_regime,
            corridor_quality_score, mean_reversion_score,
            market_health_score, market_health_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:0{index}:00",
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            spread,
            1.0,
            work_position,
            1.0,
            50.0,
            1.0,
            50.0,
            center_confidence,
            "ALIGNED",
            80.0,
            market_regime,
            order_book_pressure,
            micro_trend,
            volatility_regime,
            corridor_quality_score,
            mean_reversion_score,
            market_health_score,
            market_health_status,
        ),
    )


def test_filter_pass_diagnostics_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = FilterPassDiagnosticsEngine(database, _config()).build_summary()

    assert summary.total_entry_zone_snapshots == 0
    assert summary.buy_zone_snapshots == 0
    assert summary.sell_zone_snapshots == 0
    assert summary.warning == "Few entry-zone samples. Run longer paper validation."


def test_filter_pass_diagnostics_counts_pass_fail_unknown(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 10.0)
        _insert_snapshot(
            conn,
            1,
            85.0,
            spread=0.0003,
            center_confidence="LOW",
            market_regime="ABNORMAL",
            order_book_pressure="BID_PRESSURE",
            micro_trend="BUY_DOMINANT",
            volatility_regime="EXTREME",
            corridor_quality_score=0.0,
            mean_reversion_score=0.0,
            market_health_score=30.0,
            market_health_status="UNHEALTHY",
        )
        conn.commit()

    summary = FilterPassDiagnosticsEngine(database, _config()).build_summary()
    stats = {item.name: item for item in summary.filters}

    assert summary.total_entry_zone_snapshots == 2
    assert summary.buy_zone_snapshots == 1
    assert summary.sell_zone_snapshots == 1
    assert stats["center_confidence"].passed == 1
    assert stats["center_confidence"].failed == 1
    assert stats["spread_stability"].passed == 1
    assert stats["spread_stability"].failed == 1
    assert stats["market_health"].failed == 1
    assert stats["market_regime"].failed == 1
    assert stats["volatility_regime"].failed == 1
    assert stats["order_book_pressure"].passed == 1
    assert stats["order_book_pressure"].failed == 1
    assert stats["micro_trend"].passed == 1
    assert stats["micro_trend"].failed == 1
    assert stats["corridor_quality"].passed == 1
    assert stats["corridor_quality"].failed == 1
    assert stats["corridor_quality"].unknown == 0
    assert stats["mean_reversion_score"].passed == 1
    assert stats["mean_reversion_score"].failed == 1
    assert stats["mean_reversion_score"].unknown == 0
    assert summary.top_blocking_filters[0][1] == 1
    assert summary.latest_blocked_snapshots[0].zone == "SELL"
    assert "center_confidence" in summary.latest_blocked_snapshots[0].failed_filters
