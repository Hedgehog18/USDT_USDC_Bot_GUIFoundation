from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from config.config_manager import BotConfig
from trading.fee_engine import FeeEngine
from trading.models import CycleDirection


@dataclass(frozen=True)
class RoundedOrder:
    price: float
    quantity: float
    notional: float


@dataclass(frozen=True)
class ProfitabilityAfterRoundingResult:
    allowed: bool
    reason: str
    open_order: RoundedOrder
    close_order: RoundedOrder
    gross_profit: float
    estimated_fees: float
    net_profit: float


class ExchangeRulesEngine:
    """Правила біржі для MVP.

    Поки правила беруться з config/settings.json.
    Пізніше вони будуть підтягуватись із Binance exchangeInfo.
    """

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.fee_engine = FeeEngine(config)

    def round_price(self, price: float) -> float:
        return self._round_down(price, self.config.price_tick_size)

    def round_quantity(self, quantity: float) -> float:
        return self._round_down(quantity, self.config.quantity_step_size)

    def build_order(self, price: float, quantity: float) -> RoundedOrder:
        rounded_price = self.round_price(price)
        rounded_quantity = self.round_quantity(quantity)
        return RoundedOrder(
            price=rounded_price,
            quantity=rounded_quantity,
            notional=rounded_price * rounded_quantity,
        )

    def is_notional_allowed(self, notional: float) -> bool:
        return notional >= self.config.min_notional

    def check_profitability_after_rounding(
        self,
        direction: str,
        open_price: float,
        close_price: float,
        budget_value: float,
    ) -> ProfitabilityAfterRoundingResult:
        empty = RoundedOrder(0.0, 0.0, 0.0)

        if budget_value <= 0:
            return ProfitabilityAfterRoundingResult(
                allowed=False,
                reason="Розмір угоди має бути більшим за 0.",
                open_order=empty,
                close_order=empty,
                gross_profit=0.0,
                estimated_fees=0.0,
                net_profit=0.0,
            )

        if open_price <= 0 or close_price <= 0:
            return ProfitabilityAfterRoundingResult(
                allowed=False,
                reason="Ціни ордерів мають бути більшими за 0.",
                open_order=empty,
                close_order=empty,
                gross_profit=0.0,
                estimated_fees=0.0,
                net_profit=0.0,
            )

        open_quantity = budget_value / open_price
        open_order = self.build_order(open_price, open_quantity)

        if not self.is_notional_allowed(open_order.notional):
            return ProfitabilityAfterRoundingResult(
                allowed=False,
                reason="Open-order менший за min_notional.",
                open_order=open_order,
                close_order=empty,
                gross_profit=0.0,
                estimated_fees=0.0,
                net_profit=0.0,
            )

        close_order = self.build_order(close_price, open_order.quantity)

        if not self.is_notional_allowed(close_order.notional):
            return ProfitabilityAfterRoundingResult(
                allowed=False,
                reason="Close-order менший за min_notional.",
                open_order=open_order,
                close_order=close_order,
                gross_profit=0.0,
                estimated_fees=0.0,
                net_profit=0.0,
            )

        parsed_direction = CycleDirection(direction)

        if parsed_direction == CycleDirection.BUY_USDC:
            gross_profit = (close_order.price - open_order.price) * close_order.quantity
        else:
            gross_profit = (open_order.price - close_order.price) * close_order.quantity

        fee_rate = self.config.maker_fee_percent
        estimated_fees = (open_order.notional + close_order.notional) * fee_rate
        net_profit = gross_profit - estimated_fees

        if net_profit <= 0:
            return ProfitabilityAfterRoundingResult(
                allowed=False,
                reason="Після округлення та комісій прибуток не позитивний.",
                open_order=open_order,
                close_order=close_order,
                gross_profit=gross_profit,
                estimated_fees=estimated_fees,
                net_profit=net_profit,
            )

        return ProfitabilityAfterRoundingResult(
            allowed=True,
            reason="Profitability after rounding пройдена.",
            open_order=open_order,
            close_order=close_order,
            gross_profit=gross_profit,
            estimated_fees=estimated_fees,
            net_profit=net_profit,
        )

    @staticmethod
    def _round_down(value: float, step: float) -> float:
        if step <= 0:
            raise ValueError("Крок округлення має бути більшим за 0.")

        decimal_value = Decimal(str(value))
        decimal_step = Decimal(str(step))
        rounded = (decimal_value / decimal_step).to_integral_value(rounding=ROUND_DOWN) * decimal_step
        return float(rounded)
