from datetime import datetime
from itertools import count

from config.config_manager import BotConfig
from paper.models import PaperExecutionResult, PaperOrder, PaperOrderSide, PaperOrderStatus
from paper.paper_portfolio_manager import PaperPortfolioManager
from trading.fee_engine import FeeEngine


class PaperExchange:
    """Спрощена симуляція біржі.

    MVP-версія:
    - order виконується одразу за переданою ціною;
    - немає часткових виконань;
    - fee рахується через FeeEngine/config.
    """

    def __init__(self, config: BotConfig, portfolio_manager: PaperPortfolioManager) -> None:
        self.config = config
        self.portfolio_manager = portfolio_manager
        self.fee_engine = FeeEngine(config)
        self._ids = count(1)

    def execute_market_order(
        self,
        side: str,
        price: float,
        quantity: float,
    ) -> PaperExecutionResult:
        parsed_side = PaperOrderSide(side)
        notional = price * quantity
        fee = notional * self.config.taker_fee_percent

        order = PaperOrder(
            id=next(self._ids),
            side=parsed_side,
            price=price,
            quantity=quantity,
            notional=notional,
            status=PaperOrderStatus.CREATED,
            reason="created",
            created_at=datetime.utcnow(),
        )

        if parsed_side == PaperOrderSide.BUY_USDC:
            if not self.portfolio_manager.can_buy_usdc(notional + fee):
                order.status = PaperOrderStatus.REJECTED
                order.reason = "Недостатньо USDT для paper BUY_USDC"
                return PaperExecutionResult(order, self.portfolio_manager.get_portfolio(price), fee, order.reason)

            self.portfolio_manager.apply_buy_usdc(price, quantity, fee)

        if parsed_side == PaperOrderSide.SELL_USDC:
            if not self.portfolio_manager.can_sell_usdc(quantity):
                order.status = PaperOrderStatus.REJECTED
                order.reason = "Недостатньо USDC для paper SELL_USDC"
                return PaperExecutionResult(order, self.portfolio_manager.get_portfolio(price), fee, order.reason)

            self.portfolio_manager.apply_sell_usdc(price, quantity, fee)

        order.status = PaperOrderStatus.FILLED
        order.reason = "filled"
        order.filled_at = datetime.utcnow()

        return PaperExecutionResult(
            order=order,
            portfolio=self.portfolio_manager.get_portfolio(price),
            fee=fee,
            message="Paper order filled",
        )
