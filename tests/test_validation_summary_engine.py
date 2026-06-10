from analytics.validation_summary_engine import ValidationSummaryEngine
from storage.database_manager import DatabaseManager


def test_validation_summary_empty_database_is_no_data(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = ValidationSummaryEngine(database).build_summary()

    assert summary.overall_status == "NO_DATA"
    assert "No strategy signals" in summary.warnings
    assert summary.strategy_signals == 0
    assert summary.latest_backtest_trades == 0
    assert summary.paper_cycles == 0


def test_validation_summary_ready_for_long_paper(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO trade_signals (
                timestamp, action, reason, confidence,
                cycle_prediction_score, target_profit,
                risk_allowed, risk_reason, risk_level, cycle_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-01T00:00:00", "BUY_USDC", "test", "HIGH", 1.0, 0.1, 1, "ok", "LOW", None),
        )
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
                "BUY_USDC",
                1,
                "test",
                "Allowed",
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
                "HIGH",
                "NORMAL",
                "explain",
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO backtest_runs (
                timestamp, symbol, interval, candles, signals, trades,
                winning_trades, losing_trades, win_rate, gross_profit,
                total_fees, net_profit, roi, final_value, max_drawdown
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-01T00:00:00",
                "USDCUSDT",
                "1m",
                100,
                5,
                2,
                2,
                0,
                1.0,
                1.0,
                0.01,
                0.5,
                0.05,
                100.5,
                0.01,
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, direction, status, open_price, close_price,
                quantity, open_fee, close_fee, gross_profit, net_profit,
                opened_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-01T00:00:00",
                1,
                "BUY",
                "CLOSED",
                1.0,
                1.01,
                10.0,
                0.001,
                0.001,
                0.1,
                0.08,
                "2026-01-01T00:00:00",
                "2026-01-01T00:01:00",
            ),
        )
        conn.commit()

    summary = ValidationSummaryEngine(database).build_summary()

    assert summary.overall_status == "READY_FOR_LONG_PAPER"
    assert summary.latest_backtest_trades == 2
    assert summary.latest_backtest_net_profit == 0.5
    assert summary.paper_cycles == 1
    assert summary.paper_net_profit == 0.08
    assert summary.risk_blocked_rate == 0.0


def test_validation_summary_warns_when_entry_zones_have_no_matching_pressure(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO trade_signals (
                timestamp, action, reason, confidence,
                cycle_prediction_score, target_profit,
                risk_allowed, risk_reason, risk_level, cycle_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-01T00:00:00", "WAIT", "test", "LOW", 0.0, 0.1, 0, "blocked", "LOW", None),
        )
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
                "2026-01-01T00:00:00",
                "USDCUSDT",
                1.0,
                0.9999,
                1.0001,
                0.0002,
                1.0,
                85.0,
                1.0,
                50.0,
                1.0,
                50.0,
                "LOW",
                "ALIGNED",
                80.0,
                "NORMAL",
                "BID_PRESSURE",
                0.25,
                "SELL_DOMINANT",
            ),
        )
        conn.commit()

    summary = ValidationSummaryEngine(database, test_config).build_summary()

    assert "Entry zones detected, but order book never confirmed them." in summary.warnings
