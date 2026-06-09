from datetime import datetime
from pathlib import Path

from audit.audit_engine import AuditEngine
from market.models import MarketState
from storage.database_manager import DatabaseManager
from strategy.models import RiskResult, TradeDecision


def make_market_state() -> MarketState:
    return MarketState(
        symbol="USDCUSDT",
        price=1.0,
        bid=0.99999,
        ask=1.00001,
        spread=0.00002,
        work_low=0.9999,
        work_high=1.0001,
        work_center=1.0,
        work_position=10.0,
        short_low=0.9998,
        short_high=1.0002,
        short_center=1.0,
        short_position=20.0,
        long_low=0.9995,
        long_high=1.0005,
        long_center=1.0,
        long_position=50.0,
        center_confidence="HIGH",
        center_alignment="FLAT",
        tick_activity_score=80.0,
        center_crossing_score=80.0,
        mean_reversion_score=80.0,
        spread_stability_score=80.0,
        corridor_quality_score=80.0,
        market_activity_score=80.0,
        market_regime="ACTIVE",
        created_at=datetime.utcnow(),
    )


def test_audit_engine_saves_decision_audit(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = AuditEngine(database)

    decision = TradeDecision(
        action="BUY_USDC",
        reason="Ціна в нижній частині робочого коридору",
        confidence="HIGH",
        cycle_prediction_score=80.0,
        recommended_trade_size=10.0,
        target_profit=0.0002,
        created_at=datetime.utcnow(),
    )
    risk = RiskResult(allowed=True, reason="ok", risk_level="LOW")

    audit_id = engine.audit_decision(make_market_state(), decision, risk, cycle_id=1)

    assert audit_id > 0
    assert database.count_rows("decision_audit") == 1


def test_audit_explanation_contains_reason(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = AuditEngine(database)

    decision = TradeDecision(
        action="WAIT",
        reason="Низька активність ринку",
        confidence="LOW",
        cycle_prediction_score=20.0,
        recommended_trade_size=0,
        target_profit=0.0002,
        created_at=datetime.utcnow(),
    )
    risk = RiskResult(allowed=False, reason="Торгової дії не потрібно", risk_level="LOW")

    explanation = engine.build_explanation(make_market_state(), decision, risk)

    assert "WAIT" in explanation
    assert "Низька активність ринку" in explanation
