import pytest

from analytics.center_confidence_diagnostics_engine import CenterConfidenceDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    work_center: float,
    short_center: float,
    long_center: float,
    center_confidence: str,
    center_alignment: str = "ALIGNED",
    market_regime: str = "NORMAL",
    spread: float = 0.0001,
    order_book_pressure: str = "BALANCED",
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
            spread,
            work_center,
            work_position,
            short_center,
            50.0,
            long_center,
            50.0,
            center_confidence,
            center_alignment,
            80.0,
            market_regime,
            order_book_pressure,
            0.0,
            "NEUTRAL",
        ),
    )


def test_center_confidence_diagnostics_empty_database(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = CenterConfidenceDiagnosticsEngine(database, test_config).build_summary()

    assert summary.total_snapshots == 0
    assert summary.confidence_distribution == {
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 0,
        "UNKNOWN": 0,
    }
    assert summary.latest_low_confidence_snapshots == []


def test_center_confidence_diagnostics_builds_summary(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 10.0, 1.00, 1.10, 0.90, "LOW", "DIVERGED", "NORMAL", 0.0001)
        _insert_snapshot(conn, 1, 50.0, 1.00, 1.00, 1.00, "MEDIUM", "ALIGNED", "NORMAL", 0.0002)
        _insert_snapshot(conn, 2, 85.0, 1.20, 1.10, 1.00, "HIGH", "ALIGNED", "ACTIVE", 0.0003)
        _insert_snapshot(conn, 3, 90.0, 1.30, 1.10, 1.05, "LOW", "DIVERGED", "ACTIVE", 0.0004)
        _insert_snapshot(conn, 4, 30.0, 1.10, 1.00, 1.20, "ODD", "", "QUIET", 0.0005)
        conn.commit()

    summary = CenterConfidenceDiagnosticsEngine(database, test_config).build_summary(latest=2)

    assert summary.total_snapshots == 5
    assert summary.confidence_distribution == {
        "LOW": 2,
        "MEDIUM": 1,
        "HIGH": 1,
        "UNKNOWN": 1,
    }
    assert summary.entry_zone_confidence_distribution == {
        "LOW": 2,
        "MEDIUM": 0,
        "HIGH": 1,
        "UNKNOWN": 0,
    }
    assert summary.center_zone_confidence_distribution == {
        "LOW": 0,
        "MEDIUM": 1,
        "HIGH": 0,
        "UNKNOWN": 0,
    }
    assert summary.work_position_stats.average == pytest.approx(53.0)
    assert summary.work_position_stats.minimum == 10.0
    assert summary.work_position_stats.maximum == 90.0
    assert summary.work_short_distance_stats.average == pytest.approx(0.10)
    assert summary.work_long_distance_stats.average == pytest.approx(0.13)
    assert summary.short_long_distance_stats.average == pytest.approx(0.11)
    assert summary.center_alignment_distribution == {
        "ALIGNED": 2,
        "DIVERGED": 2,
        "UNKNOWN": 1,
    }
    assert [item.work_position for item in summary.latest_low_confidence_snapshots] == [90.0, 10.0]
    assert summary.latest_low_confidence_snapshots[0].order_book_pressure == "BALANCED"
