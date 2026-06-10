from analytics.risk_diagnostics_engine import RiskDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_audit(conn, timestamp: str, decision: str, allowed: int, reason: str, risk_reason: str) -> None:
    conn.execute(
        """
        INSERT INTO decision_audit (
            timestamp, decision, allowed, reason, risk_reason, symbol,
            price, bid, ask, spread, work_position, short_position,
            long_position, market_activity_score, cycle_prediction_score,
            center_confidence, market_regime, explanation, cycle_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            decision,
            allowed,
            reason,
            risk_reason,
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            0.0002,
            50.0,
            50.0,
            50.0,
            10.0,
            1.0,
            "LOW",
            "NORMAL",
            "explain",
            None,
        ),
    )


def test_risk_diagnostics_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = RiskDiagnosticsEngine(database).build_summary()

    assert summary.total_audited_decisions == 0
    assert summary.allowed_count == 0
    assert summary.blocked_count == 0
    assert summary.blocked_rate == 0.0
    assert summary.top_risk_reasons == []
    assert summary.blocked_action_distribution == {}
    assert summary.latest_blocked_decisions == []


def test_risk_diagnostics_aggregates_audit_rows(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_audit(conn, "2026-01-01T00:00:00", "BUY_USDC", 1, "buy", "Allowed")
        _insert_audit(conn, "2026-01-01T00:01:00", "WAIT", 0, "wait", "No trade needed")
        _insert_audit(conn, "2026-01-01T00:02:00", "SELL_USDC", 0, "sell", "Exposure limit")
        _insert_audit(conn, "2026-01-01T00:03:00", "SELL_USDC", 0, "sell again", "Exposure limit")
        conn.commit()

    summary = RiskDiagnosticsEngine(database).build_summary(top=2, latest=2)

    assert summary.total_audited_decisions == 4
    assert summary.allowed_count == 1
    assert summary.blocked_count == 3
    assert summary.blocked_rate == 0.75
    assert summary.top_risk_reasons == [("Exposure limit", 2), ("No trade needed", 1)]
    assert summary.blocked_action_distribution == {"SELL_USDC": 2, "WAIT": 1}
    assert [item.decision for item in summary.latest_blocked_decisions] == ["SELL_USDC", "SELL_USDC"]
    assert summary.latest_blocked_decisions[0].risk_reason == "Exposure limit"


def test_risk_diagnostics_cleans_mojibake_reasons(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    reason = "Торгової дії не потрібно"
    risk_reason = "Низька надійність центру"

    with database.connect() as conn:
        _insert_audit(
            conn,
            "2026-01-01T00:00:00",
            "WAIT",
            0,
            reason.encode("utf-8").decode("cp1251"),
            risk_reason.encode("utf-8").decode("cp1251"),
        )
        conn.commit()

    summary = RiskDiagnosticsEngine(database).build_summary()

    assert summary.top_risk_reasons == [(risk_reason, 1)]
    assert summary.latest_blocked_decisions[0].reason == reason
