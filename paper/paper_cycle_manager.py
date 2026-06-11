from datetime import datetime
from itertools import count

from config.config_manager import BotConfig
from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from paper.paper_exchange import PaperExchange
from trading.fee_engine import FeeEngine


class PaperCycleManager:
    """Керує paper-циклами open -> close.

    MVP-версія:
    - відкриває позицію market order;
    - закриває при досягненні target_profit;
    - розраховує gross/net PnL.
    """

    def __init__(self, config: BotConfig, exchange: PaperExchange) -> None:
        self.config = config
        self.exchange = exchange
        self.fee_engine = FeeEngine(config)
        self._ids = count(1)
        self.active_cycles: list[PaperCycle] = []
        self.closed_cycles: list[PaperCycle] = []

    def has_active_cycle(self) -> bool:
        return bool(self.active_cycles)

    def open_cycle(self, direction: str, price: float, target_profit: float | None = None) -> PaperCycle | None:
        if self.has_active_cycle():
            return None

        effective_target_profit = self.config.target_profit if target_profit is None else target_profit
        portfolio = self.exchange.portfolio_manager.get_portfolio(price)
        trade_value = portfolio.total_value * self.config.trade_size_percent
        quantity = trade_value / price

        execution = self.exchange.execute_market_order(direction, price, quantity)

        if execution.order.status.value != "FILLED":
            return None

        close_price = (
            price * (1 + effective_target_profit)
            if direction == "BUY_USDC"
            else price * (1 - effective_target_profit)
        )

        cycle = PaperCycle(
            id=next(self._ids),
            direction=PaperOrderSide(direction),
            status=PaperCycleStatus.OPEN,
            open_price=price,
            close_price=close_price,
            quantity=quantity,
            open_fee=execution.fee,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=datetime.utcnow(),
        )
        self.active_cycles.append(cycle)
        return cycle

    def try_close_cycle(self, price: float) -> PaperCycle | None:
        if not self.active_cycles:
            return None

        cycle = self.active_cycles[0]

        if cycle.direction == PaperOrderSide.BUY_USDC and price < cycle.close_price:
            return None

        if cycle.direction == PaperOrderSide.SELL_USDC and price > cycle.close_price:
            return None

        close_side = (
            PaperOrderSide.SELL_USDC.value
            if cycle.direction == PaperOrderSide.BUY_USDC
            else PaperOrderSide.BUY_USDC.value
        )

        execution = self.exchange.execute_market_order(close_side, price, cycle.quantity)

        if execution.order.status.value != "FILLED":
            cycle.status = PaperCycleStatus.FAILED
            return cycle

        profit = self.fee_engine.calculate_profit(
            direction=cycle.direction.value,
            open_price=cycle.open_price,
            close_price=price,
            quantity=cycle.quantity,
            use_taker_fee=True,
        )

        cycle.close_price = price
        cycle.close_fee = execution.fee
        cycle.gross_profit = profit.gross_profit
        cycle.net_profit = profit.net_profit
        cycle.status = PaperCycleStatus.CLOSED
        cycle.closed_at = datetime.utcnow()

        self.active_cycles = [item for item in self.active_cycles if item.id != cycle.id]
        self.closed_cycles.append(cycle)

        return cycle
