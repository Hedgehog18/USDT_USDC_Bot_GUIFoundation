from config.config_manager import BotConfig
from portfolio.models import BotBudget
from strategy.models import RiskResult, TradeDecision
from trading.exchange_rules_engine import ExchangeRulesEngine


class RiskManager:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.exchange_rules = ExchangeRulesEngine(config)

    def validate_decision(
        self,
        decision: TradeDecision,
        budget: BotBudget | None = None,
        current_price: float = 1.0,
    ) -> RiskResult:
        if decision.action == "SAFE_WAIT":
            return RiskResult(False, "Система перебуває в безпечному очікуванні", "HIGH")

        if decision.action == "WAIT":
            return RiskResult(False, "Торгової дії не потрібно", "LOW")

        if decision.cycle_prediction_score < self.config.min_cycle_prediction_score:
            return RiskResult(False, "Низький Cycle Prediction Score", "MEDIUM")

        if budget is None:
            return RiskResult(False, "Бюджет бота не передано в RiskManager", "HIGH")

        trade_size = budget.total_value * self.config.trade_size_percent

        if decision.action == "BUY_USDC":
            min_reserve = budget.total_value * self.config.min_usdt_reserve_percent
            if budget.usdt_budget - trade_size < min_reserve:
                return RiskResult(False, "Після купівлі буде порушено резерв USDT", "MEDIUM")

        if decision.action == "SELL_USDC":
            min_reserve = budget.total_value * self.config.min_usdc_reserve_percent
            if budget.usdc_value - trade_size < min_reserve:
                return RiskResult(False, "Після продажу буде порушено резерв USDC", "MEDIUM")

        if decision.action == "BUY_USDC":
            open_price = current_price
            close_price = current_price * (1 + decision.target_profit)
        else:
            open_price = current_price
            close_price = current_price * (1 - decision.target_profit)

        profitability = self.exchange_rules.check_profitability_after_rounding(
            direction=decision.action,
            open_price=open_price,
            close_price=close_price,
            budget_value=trade_size,
        )

        if not profitability.allowed:
            return RiskResult(False, profitability.reason, "MEDIUM")

        return RiskResult(True, "Базові перевірки бюджету, біржових правил та ризику пройдено", "LOW")
