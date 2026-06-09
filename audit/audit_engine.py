from datetime import datetime

from audit.models import DecisionAuditRecord
from market.models import MarketState
from storage.database_manager import DatabaseManager
from strategy.models import RiskResult, TradeDecision


class AuditEngine:
    """Зберігає пояснення торгових рішень.

    AuditEngine потрібен, щоб через день, місяць або рік можна було відповісти:
    - чому бот відкрив цикл;
    - чому бот чекав;
    - чому RiskManager заблокував сигнал.
    """

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def audit_decision(
        self,
        market_state: MarketState,
        decision: TradeDecision,
        risk_result: RiskResult,
        cycle_id: int | None = None,
    ) -> int:
        explanation = self.build_explanation(market_state, decision, risk_result)

        record = DecisionAuditRecord(
            timestamp=datetime.utcnow(),
            decision=decision.action,
            allowed=risk_result.allowed,
            reason=decision.reason,
            risk_reason=risk_result.reason,
            symbol=market_state.symbol,
            price=market_state.price,
            bid=market_state.bid,
            ask=market_state.ask,
            spread=market_state.spread,
            work_position=market_state.work_position,
            short_position=market_state.short_position,
            long_position=market_state.long_position,
            market_activity_score=market_state.market_activity_score,
            cycle_prediction_score=decision.cycle_prediction_score,
            center_confidence=market_state.center_confidence,
            market_regime=market_state.market_regime,
            explanation=explanation,
            cycle_id=cycle_id,
        )

        return self.database.save_decision_audit(record)

    @staticmethod
    def build_explanation(
        market_state: MarketState,
        decision: TradeDecision,
        risk_result: RiskResult,
    ) -> str:
        return (
            f"Рішення: {decision.action}. "
            f"Причина рішення: {decision.reason}. "
            f"RiskManager: {'дозволено' if risk_result.allowed else 'заблоковано'}. "
            f"Причина RiskManager: {risk_result.reason}. "
            f"Work Position: {market_state.work_position:.2f}%. "
            f"Short Position: {market_state.short_position:.2f}%. "
            f"Long Position: {market_state.long_position:.2f}%. "
            f"Market Activity Score: {market_state.market_activity_score:.2f}. "
            f"Cycle Prediction Score: {decision.cycle_prediction_score:.2f}. "
            f"Center Confidence: {market_state.center_confidence}. "
            f"Market Regime: {market_state.market_regime}. "
            f"OrderBook Pressure: {market_state.order_book_pressure} ({market_state.order_book_imbalance:.4f}). "
            f"Micro Trend: {market_state.micro_trend} ({market_state.trade_volume_delta:.4f}). "
            f"Volatility: {market_state.volatility_regime} ({market_state.relative_volatility:.8f}). "
            f"Market Health: {market_state.market_health_status} ({market_state.market_health_score:.2f}) - {market_state.market_health_reason}."
        )
