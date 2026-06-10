from analytics.strategy_validation_engine import StrategyValidationEngine
from storage.database_manager import DatabaseManager


def test_strategy_validation_summary_empty_database(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = StrategyValidationEngine(database).build_summary()

    assert summary.total_signals == 0
    assert summary.buy_signals == 0
    assert summary.sell_signals == 0
    assert summary.average_confidence == 0.0
    assert summary.average_spread == 0.0
    assert summary.average_volatility == 0.0
    assert summary.market_regime_distribution == {}


def test_strategy_validation_summary_aggregates_signals_and_market(tmp_path):
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
            INSERT INTO trade_signals (
                timestamp, action, reason, confidence,
                cycle_prediction_score, target_profit,
                risk_allowed, risk_reason, risk_level, cycle_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-01T00:01:00", "SELL_USDC", "test", "LOW", 1.0, 0.1, 1, "ok", "LOW", None),
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
                relative_volatility
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-01-01T00:00:00",
                "USDCUSDT",
                1.0,
                0.9999,
                1.0001,
                0.0002,
                1.0,
                50.0,
                1.0,
                50.0,
                1.0,
                50.0,
                "HIGH",
                "ALIGNED",
                80.0,
                "NORMAL",
                0.00001,
            ),
        )
        conn.commit()

    summary = StrategyValidationEngine(database).build_summary()

    assert summary.total_signals == 2
    assert summary.buy_signals == 1
    assert summary.sell_signals == 1
    assert summary.average_confidence == 0.5
    assert summary.average_spread == 0.0002
    assert summary.average_volatility == 0.00001
    assert summary.market_regime_distribution == {"NORMAL": 1}
