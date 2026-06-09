from dataclasses import dataclass

from config.config_manager import BotConfig
from trading.models import CycleDirection


@dataclass(frozen=True)
class FeeCalculation:
    open_fee: float
    close_fee: float
    total_fee: float


@dataclass(frozen=True)
class ProfitCalculation:
    gross_profit: float
    fees: FeeCalculation
    net_profit: float


class FeeEngine:
    """Розрахунок комісій і прибутку.

    MVP-версія:
    - використовує maker fee з конфігурації;
    - taker fee залишений у конфігурації для майбутніх сценаріїв;
    - працює з USDC/USDT як майже паритетною парою.
    """

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def calculate_fees(
        self,
        open_notional: float,
        close_notional: float,
        use_taker_fee: bool = False,
    ) -> FeeCalculation:
        fee_rate = self.config.taker_fee_percent if use_taker_fee else self.config.maker_fee_percent

        open_fee = open_notional * fee_rate
        close_fee = close_notional * fee_rate

        return FeeCalculation(
            open_fee=open_fee,
            close_fee=close_fee,
            total_fee=open_fee + close_fee,
        )

    def calculate_gross_profit(
        self,
        direction: str,
        open_price: float,
        close_price: float,
        quantity: float,
    ) -> float:
        parsed_direction = CycleDirection(direction)

        if parsed_direction == CycleDirection.BUY_USDC:
            return (close_price - open_price) * quantity

        return (open_price - close_price) * quantity

    def calculate_profit(
        self,
        direction: str,
        open_price: float,
        close_price: float,
        quantity: float,
        use_taker_fee: bool = False,
    ) -> ProfitCalculation:
        open_notional = open_price * quantity
        close_notional = close_price * quantity

        gross_profit = self.calculate_gross_profit(
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            quantity=quantity,
        )

        fees = self.calculate_fees(
            open_notional=open_notional,
            close_notional=close_notional,
            use_taker_fee=use_taker_fee,
        )

        return ProfitCalculation(
            gross_profit=gross_profit,
            fees=fees,
            net_profit=gross_profit - fees.total_fee,
        )
