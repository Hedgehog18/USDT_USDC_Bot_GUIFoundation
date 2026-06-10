import pytest

from analytics.entry_zone_diagnostics_engine import EntryZoneDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    spread: float,
    market_health_score: float,
    market_regime: str,
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
            market_health_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "HIGH",
            "ALIGNED",
            80.0,
            market_regime,
            market_health_score,
        ),
    )


def test_entry_zone_diagnostics_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = EntryZoneDiagnosticsEngine(database).build_summary()

    assert summary.total_snapshots == 0
    assert summary.average_work_position == 0.0
    assert summary.potential_buy_zone_count == 0
    assert summary.potential_sell_zone_count == 0
    assert summary.center_zone_count == 0
    assert summary.market_regime_distribution == {}


def test_entry_zone_diagnostics_builds_summary(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 5.0, 0.0001, 80.0, "NORMAL")
        _insert_snapshot(conn, 1, 20.0, 0.0002, 90.0, "NORMAL")
        _insert_snapshot(conn, 2, 50.0, 0.0003, 100.0, "ACTIVE")
        _insert_snapshot(conn, 3, 85.0, 0.0004, 70.0, "VOLATILE")
        _insert_snapshot(conn, 4, 100.0, 0.0005, 60.0, "VOLATILE")
        conn.commit()

    summary = EntryZoneDiagnosticsEngine(database).build_summary()

    assert summary.total_snapshots == 5
    assert summary.average_work_position == pytest.approx(52.0)
    assert summary.min_work_position == 5.0
    assert summary.max_work_position == 100.0
    assert summary.median_work_position == 50.0
    assert summary.buckets == {
        "0-10": 1,
        "10-20": 0,
        "20-30": 1,
        "30-40": 0,
        "40-60": 1,
        "60-70": 0,
        "70-80": 0,
        "80-90": 1,
        "90-100": 1,
    }
    assert summary.potential_buy_zone_count == 2
    assert summary.potential_sell_zone_count == 2
    assert summary.center_zone_count == 1
    assert summary.average_spread == pytest.approx(0.0003)
    assert summary.average_market_health_score == pytest.approx(80.0)
    assert summary.market_regime_distribution == {"NORMAL": 2, "VOLATILE": 2, "ACTIVE": 1}
