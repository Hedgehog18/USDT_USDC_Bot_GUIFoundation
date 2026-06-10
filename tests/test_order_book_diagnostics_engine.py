import pytest

from analytics.order_book_diagnostics_engine import OrderBookDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    pressure: str,
    imbalance: float,
    micro_trend: str = "NEUTRAL",
    center_confidence: str = "LOW",
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
            order_book_pressure, order_book_imbalance,
            micro_trend
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:0{index}:00",
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            0.0002,
            1.0,
            work_position,
            1.0,
            50.0,
            1.0,
            50.0,
            center_confidence,
            "ALIGNED",
            80.0,
            "NORMAL",
            pressure,
            imbalance,
            micro_trend,
        ),
    )


def test_order_book_diagnostics_empty_database(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = OrderBookDiagnosticsEngine(database, test_config).build_summary()

    assert summary.total_snapshots == 0
    assert summary.entry_zone_snapshots == 0
    assert summary.order_book_pressure_distribution == {
        "BALANCED": 0,
        "BID_PRESSURE": 0,
        "ASK_PRESSURE": 0,
        "UNKNOWN": 0,
    }
    assert summary.latest_entry_zone_snapshots == []


def test_order_book_diagnostics_builds_entry_zone_summary(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 10.0, "BID_PRESSURE", 0.5, "BUY_DOMINANT", "HIGH")
        _insert_snapshot(conn, 1, 15.0, "ASK_PRESSURE", -0.2, "SELL_DOMINANT", "LOW")
        _insert_snapshot(conn, 2, 50.0, "BALANCED", 0.0)
        _insert_snapshot(conn, 3, 85.0, "ASK_PRESSURE", -0.4, "SELL_DOMINANT", "MEDIUM")
        _insert_snapshot(conn, 4, 90.0, "BID_PRESSURE", 0.3, "BUY_DOMINANT", "LOW")
        _insert_snapshot(conn, 5, 95.0, "UNKNOWN", 0.0)
        conn.commit()

    summary = OrderBookDiagnosticsEngine(database, test_config).build_summary(latest=3)

    assert summary.total_snapshots == 6
    assert summary.entry_zone_snapshots == 5
    assert summary.order_book_pressure_distribution == {
        "BALANCED": 1,
        "BID_PRESSURE": 2,
        "ASK_PRESSURE": 2,
        "UNKNOWN": 1,
    }
    assert summary.buy_zone_distribution == {
        "BID_PRESSURE": 1,
        "ASK_PRESSURE": 1,
        "BALANCED": 0,
        "UNKNOWN": 0,
    }
    assert summary.sell_zone_distribution == {
        "BID_PRESSURE": 1,
        "ASK_PRESSURE": 1,
        "BALANCED": 0,
        "UNKNOWN": 1,
    }
    assert summary.average_order_book_imbalance == pytest.approx(0.04)
    assert summary.min_order_book_imbalance == -0.4
    assert summary.max_order_book_imbalance == 0.5
    assert [item.direction_candidate for item in summary.latest_entry_zone_snapshots] == ["SELL", "SELL", "SELL"]
    assert summary.latest_entry_zone_snapshots[0].work_position == 95.0
