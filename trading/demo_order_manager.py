from trading.models import Cycle, CycleDirection


class DemoOrderManager:
    def can_fill_open_order(self, cycle: Cycle, bid: float, ask: float) -> bool:
        if cycle.direction == CycleDirection.BUY_USDC:
            return ask <= cycle.open_price
        if cycle.direction == CycleDirection.SELL_USDC:
            return bid >= cycle.open_price
        return False

    def can_fill_close_order(self, cycle: Cycle, bid: float, ask: float) -> bool:
        if cycle.direction == CycleDirection.BUY_USDC:
            return bid >= cycle.close_price
        if cycle.direction == CycleDirection.SELL_USDC:
            return ask <= cycle.close_price
        return False
