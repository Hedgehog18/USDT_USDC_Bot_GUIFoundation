from analytics.decision_diagnostics_engine import DecisionDiagnosticsEngine
from storage.database_manager import DatabaseManager


def test_decision_diagnostics_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = DecisionDiagnosticsEngine(database).build_summary()

    assert summary.total_decisions == 0
    assert summary.buy_count == 0
    assert summary.sell_count == 0
    assert summary.wait_count == 0
    assert summary.top_wait_reasons == []
    assert summary.confidence_distribution == {}
    assert summary.risk_blocked_count == 0


def test_decision_diagnostics_aggregates_trade_signals(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        rows = [
            ("BUY_USDC", "buy reason", "HIGH", 1),
            ("SELL_USDC", "sell reason", "LOW", 1),
            ("WAIT", "wait reason", "LOW", 0),
            ("WAIT", "wait reason", "MEDIUM", 0),
        ]
        for index, (action, reason, confidence, risk_allowed) in enumerate(rows):
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
                    risk_allowed,
                    "risk",
                    "LOW",
                    None,
                ),
            )
        conn.commit()

    summary = DecisionDiagnosticsEngine(database).build_summary()

    assert summary.total_decisions == 4
    assert summary.buy_count == 1
    assert summary.sell_count == 1
    assert summary.wait_count == 2
    assert summary.top_wait_reasons == [("wait reason", 2)]
    assert summary.top_buy_reasons == [("buy reason", 1)]
    assert summary.top_sell_reasons == [("sell reason", 1)]
    assert summary.confidence_distribution == {"HIGH": 1, "LOW": 2, "MEDIUM": 1}
    assert summary.risk_blocked_count == 2


def test_decision_diagnostics_falls_back_to_decision_audit(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
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
                "2026-01-01T00:00:00",
                "WAIT",
                0,
                "audit wait",
                "risk",
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
        conn.commit()

    summary = DecisionDiagnosticsEngine(database).build_summary()

    assert summary.total_decisions == 1
    assert summary.wait_count == 1
    assert summary.top_wait_reasons == [("audit wait", 1)]
    assert summary.confidence_distribution == {"LOW": 1}
    assert summary.risk_blocked_count == 1
