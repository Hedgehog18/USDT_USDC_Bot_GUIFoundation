import pytest

from analytics.confidence_diagnostics_engine import ConfidenceDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_signal(conn, index: int, action: str, reason: str, confidence: str) -> None:
    conn.execute(
        """
        INSERT INTO trade_signals (
            timestamp, action, reason, confidence,
            cycle_prediction_score, target_profit,
            risk_allowed, risk_reason, risk_level, cycle_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:0{index}:00",
            action,
            reason,
            confidence,
            1.0,
            0.1,
            0,
            "risk",
            "LOW",
            None,
        ),
    )


def _insert_market_snapshot(conn, index: int, work_position: float, market_regime: str) -> None:
    conn.execute(
        """
        INSERT INTO market_snapshots (
            timestamp, symbol, price, bid, ask, spread, work_center,
            work_position, short_center, short_position, long_center,
            long_position, center_confidence, center_alignment,
            market_activity_score, market_regime
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:0{index}:30",
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
            "LOW",
            "CENTERED",
            10.0,
            market_regime,
        ),
    )


def test_confidence_diagnostics_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = ConfidenceDiagnosticsEngine(database).build_summary()

    assert summary.total_decisions == 0
    assert summary.average_confidence == 0.0
    assert summary.confidence_buckets == {
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 0,
    }
    assert summary.top_wait_reasons == []
    assert summary.center_distance.average == 0.0
    assert summary.market_regime_distribution == {}


def test_confidence_diagnostics_builds_summary(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_signal(conn, 0, "WAIT", "low center", "LOW")
        _insert_signal(conn, 1, "WAIT", "low center", "MEDIUM")
        _insert_signal(conn, 2, "BUY_USDC", "buy", "HIGH")
        _insert_signal(conn, 3, "SELL_USDC", "sell", "0.9")
        _insert_market_snapshot(conn, 0, 50.0, "NORMAL")
        _insert_market_snapshot(conn, 1, 70.0, "NORMAL")
        _insert_market_snapshot(conn, 2, 20.0, "ACTIVE")
        conn.commit()

    summary = ConfidenceDiagnosticsEngine(database).build_summary(top=2)

    assert summary.total_decisions == 4
    assert summary.average_confidence == 0.6
    assert summary.min_confidence == 0.25
    assert summary.max_confidence == 0.9
    assert summary.median_confidence == 0.625
    assert summary.confidence_buckets == {
        "0.0-0.2": 0,
        "0.2-0.4": 1,
        "0.4-0.6": 1,
        "0.6-0.8": 1,
        "0.8-1.0": 1,
    }
    assert summary.top_wait_reasons == [("low center", 2)]
    assert summary.center_distance.average == pytest.approx((0.0 + 20.0 + 30.0) / 3)
    assert summary.center_distance.minimum == 0.0
    assert summary.center_distance.maximum == 30.0
    assert summary.market_regime_distribution == {"NORMAL": 2, "ACTIVE": 1}
