from pathlib import Path

from analytics.risk_profitability_diagnostics_engine import RiskProfitabilityDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _with_symbol(test_config, symbol: str):
    return test_config.__class__(**{
        **test_config.__dict__,
        "symbol": symbol,
    })


def test_risk_profitability_detail_uses_zero_fee_override_for_usdcusdt(test_config):
    engine = RiskProfitabilityDiagnosticsEngine(test_config)

    detail = engine.build_detail(
        action="SELL_USDC",
        current_price=1.0005,
        budget_total_value=100.0,
        reason="blocked",
    )

    assert detail.action == "SELL_USDC"
    assert detail.trade_size == 10.0
    assert detail.quantity_before_rounding > detail.quantity_after_rounding
    assert detail.gross_profit >= 0
    assert detail.estimated_fees == 0.0
    assert detail.net_profit == detail.gross_profit
    assert detail.allowed is True
    assert detail.min_notional == test_config.min_notional


def test_risk_profitability_detail_explains_small_profit_block_for_config_fee_symbol(test_config):
    engine = RiskProfitabilityDiagnosticsEngine(_with_symbol(test_config, "BTCUSDT"))

    detail = engine.build_detail(
        action="SELL_USDC",
        current_price=1.0005,
        budget_total_value=100.0,
        reason="blocked",
    )

    assert detail.estimated_fees > 0
    assert detail.net_profit <= 0
    assert detail.allowed is False
    assert detail.min_notional == test_config.min_notional


def test_risk_profitability_report_uses_blocked_buy_sell_audit_rows(tmp_path: Path, test_config):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO decision_audit (
                timestamp, decision, allowed, reason, risk_reason,
                symbol, price, bid, ask, spread,
                work_position, short_position, long_position,
                market_activity_score, cycle_prediction_score,
                center_confidence, market_regime,
                explanation, cycle_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-11T10:00:00",
                "SELL_USDC",
                0,
                "profile sell",
                "net not positive",
                "USDCUSDT",
                1.0005,
                1.00049,
                1.00051,
                0.00002,
                85.0,
                80.0,
                75.0,
                50.0,
                100.0,
                "LOW",
                "NORMAL",
                "explanation",
                None,
            ),
        )
        conn.commit()

    report = RiskProfitabilityDiagnosticsEngine(test_config, database).build_report(limit=5)

    assert report.estimated_from_config is True
    assert len(report.details) == 1
    assert report.details[0].action == "SELL_USDC"
    assert report.details[0].timestamp == "2026-06-11T10:00:00"
    assert report.details[0].decision_reason == "profile sell"
