from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.exchange_rules_engine import ExchangeRulesEngine


@dataclass(frozen=True)
class RiskProfitabilityDetail:
    action: str
    current_price: float
    target_price: float
    budget_total_value: float
    trade_size: float
    quantity_before_rounding: float
    quantity_after_rounding: float
    open_notional_before_rounding: float
    open_notional_after_rounding: float
    rounding_impact: float
    gross_profit: float
    estimated_fees: float
    net_profit: float
    min_notional: float
    allowed: bool
    reason: str
    timestamp: str | None = None
    decision_reason: str | None = None


@dataclass(frozen=True)
class RiskProfitabilityDiagnosticsReport:
    details: list[RiskProfitabilityDetail]
    estimated_from_config: bool


class RiskProfitabilityDiagnosticsEngine:
    def __init__(self, config: BotConfig, database: DatabaseManager | None = None) -> None:
        self.config = config
        self.database = database
        self.exchange_rules = ExchangeRulesEngine(config)

    def build_detail(
        self,
        action: str,
        current_price: float,
        budget_total_value: float,
        reason: str = "",
        timestamp: str | None = None,
        decision_reason: str | None = None,
    ) -> RiskProfitabilityDetail:
        action = clean_display_text(action)
        target_price = self._target_price(action, current_price)
        trade_size = budget_total_value * self.config.trade_size_percent
        quantity_before_rounding = trade_size / current_price if current_price > 0 else 0.0

        profitability = self.exchange_rules.check_profitability_after_rounding(
            direction=action,
            open_price=current_price,
            close_price=target_price,
            budget_value=trade_size,
        )

        open_notional_before_rounding = current_price * quantity_before_rounding
        open_notional_after_rounding = profitability.open_order.notional

        return RiskProfitabilityDetail(
            action=action,
            current_price=current_price,
            target_price=target_price,
            budget_total_value=budget_total_value,
            trade_size=trade_size,
            quantity_before_rounding=quantity_before_rounding,
            quantity_after_rounding=profitability.open_order.quantity,
            open_notional_before_rounding=open_notional_before_rounding,
            open_notional_after_rounding=open_notional_after_rounding,
            rounding_impact=open_notional_before_rounding - open_notional_after_rounding,
            gross_profit=profitability.gross_profit,
            estimated_fees=profitability.estimated_fees,
            net_profit=profitability.net_profit,
            min_notional=self.config.min_notional,
            allowed=profitability.allowed,
            reason=clean_display_text(reason or profitability.reason),
            timestamp=clean_display_text(timestamp) if timestamp else None,
            decision_reason=clean_display_text(decision_reason) if decision_reason else None,
        )

    def build_report(self, limit: int = 10) -> RiskProfitabilityDiagnosticsReport:
        if self.database is None:
            return RiskProfitabilityDiagnosticsReport(details=[], estimated_from_config=True)

        details = [
            self.build_detail(
                action=row["decision"],
                current_price=row["price"],
                budget_total_value=(
                    self.config.backtest_initial_usdt
                    + self.config.backtest_initial_usdc * row["price"]
                ),
                reason=row["risk_reason"],
                timestamp=row["timestamp"],
                decision_reason=row["reason"],
            )
            for row in self._load_blocked_buy_sell_decisions(limit)
        ]

        return RiskProfitabilityDiagnosticsReport(
            details=details,
            estimated_from_config=True,
        )

    def _load_blocked_buy_sell_decisions(self, limit: int) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, decision, reason, risk_reason, price
                FROM decision_audit
                WHERE allowed = 0
                  AND decision IN ('BUY_USDC', 'SELL_USDC')
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "timestamp": clean_display_text(timestamp),
                "decision": clean_display_text(decision),
                "reason": clean_display_text(reason),
                "risk_reason": clean_display_text(risk_reason),
                "price": float(price),
            }
            for timestamp, decision, reason, risk_reason, price in rows
        ]

    def _target_price(self, action: str, current_price: float) -> float:
        if action == "BUY_USDC":
            return current_price * (1 + self.config.target_profit)
        if action == "SELL_USDC":
            return current_price * (1 - self.config.target_profit)
        raise ValueError(f"Unsupported action for risk profitability diagnostics: {action}")
