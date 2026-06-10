from analytics.strategy_tuning_report_engine import StrategyTuningReportEngine
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


def test_strategy_tuning_report_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = StrategyTuningReportEngine(database).build_report()

    assert report.total_signals == 0
    assert [item.total_passed for item in report.thresholds] == [0, 0, 0, 0, 0]


def test_strategy_tuning_report_simulates_confidence_thresholds(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_signal(conn, 0, "WAIT", "low center", "LOW")
        _insert_signal(conn, 1, "WAIT", "low activity", "0.35")
        _insert_signal(conn, 2, "BUY_USDC", "buy zone", "MEDIUM")
        _insert_signal(conn, 3, "SELL_USDC", "sell zone", "HIGH")
        conn.commit()

    report = StrategyTuningReportEngine(database).build_report(top=2)

    by_threshold = {item.threshold: item for item in report.thresholds}
    assert report.total_signals == 4
    assert by_threshold[0.2].total_passed == 4
    assert by_threshold[0.2].pass_rate == 1.0
    assert by_threshold[0.2].buy_candidates == 1
    assert by_threshold[0.2].sell_candidates == 1
    assert by_threshold[0.2].wait_still_blocked == 0
    assert by_threshold[0.4].total_passed == 2
    assert by_threshold[0.4].top_remaining_reasons == [("low center", 1), ("low activity", 1)]
    assert by_threshold[0.6].total_passed == 1
    assert by_threshold[0.6].sell_candidates == 1
    assert by_threshold[0.6].wait_still_blocked == 2
