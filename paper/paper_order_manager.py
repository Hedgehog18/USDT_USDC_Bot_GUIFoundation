from config.config_manager import BotConfig
from market.models import MarketState
from paper.models import PaperExecutionResult
from paper.paper_exchange import PaperExchange


class PaperOrderManager:
    def __init__(self, config: BotConfig, exchange: PaperExchange) -> None:
        self.config = config
        self.exchange = exchange

    def execute_decision(self, action: str, market_state: MarketState) -> PaperExecutionResult | None:
        if action not in {"BUY_USDC", "SELL_USDC"}:
            return None

        portfolio = self.exchange.portfolio_manager.get_portfolio(market_state.price)
        trade_value = portfolio.total_value * self.config.trade_size_percent
        quantity = trade_value / market_state.price

        return self.exchange.execute_market_order(
            side=action,
            price=market_state.price,
            quantity=quantity,
        )
