from datetime import datetime
from itertools import count

from trading.models import Cycle, CycleDirection, CycleStatus, CycleTimeStatus


class CycleManager:
    def __init__(self) -> None:
        self._id_sequence = count(1)
        self.active_cycles: list[Cycle] = []
        self.closed_cycles: list[Cycle] = []

    def has_active_cycles(self) -> bool:
        return len(self.active_cycles) > 0

    def create_cycle(self, mode: str, direction: str, current_price: float, amount: float, target_profit: float) -> Cycle:
        if self.has_active_cycles():
            raise RuntimeError("У MVP дозволено лише один активний цикл.")

        parsed_direction = CycleDirection(direction)
        close_price = current_price * (1 + target_profit) if parsed_direction == CycleDirection.BUY_USDC else current_price * (1 - target_profit)

        cycle = Cycle(
            id=next(self._id_sequence),
            mode=mode,
            direction=parsed_direction,
            status=CycleStatus.CREATED,
            time_status=CycleTimeStatus.NORMAL,
            open_price=current_price,
            close_price=close_price,
            amount=amount,
            target_profit=target_profit,
            expected_profit=amount * target_profit,
            actual_profit=None,
            created_at=datetime.utcnow(),
        )
        self.active_cycles.append(cycle)
        return cycle

    def add_recovered_cycle(self, cycle: Cycle) -> None:
        if cycle.status != CycleStatus.CLOSED:
            self.active_cycles.append(cycle)

    def place_open_order(self, cycle: Cycle) -> Cycle:
        cycle.status = CycleStatus.OPEN_ORDER_PLACED
        return cycle

    def mark_open_filled(self, cycle: Cycle) -> Cycle:
        cycle.status = CycleStatus.OPEN_ORDER_FILLED
        cycle.open_filled_at = datetime.utcnow()
        return cycle

    def place_close_order(self, cycle: Cycle) -> Cycle:
        if cycle.status != CycleStatus.OPEN_ORDER_FILLED:
            raise RuntimeError("Close-order можна створити лише після виконання open-order.")
        cycle.status = CycleStatus.CLOSE_ORDER_PLACED
        return cycle

    def mark_close_filled(self, cycle: Cycle) -> Cycle:
        if cycle.status != CycleStatus.CLOSE_ORDER_PLACED:
            raise RuntimeError("Close-order має бути створений перед закриттям циклу.")

        cycle.status = CycleStatus.CLOSE_ORDER_FILLED
        cycle.close_filled_at = datetime.utcnow()
        cycle.closed_at = cycle.close_filled_at

        if cycle.direction == CycleDirection.BUY_USDC:
            cycle.actual_profit = (cycle.close_price - cycle.open_price) * cycle.amount
        else:
            cycle.actual_profit = (cycle.open_price - cycle.close_price) * cycle.amount

        cycle.status = CycleStatus.CLOSED
        self.active_cycles = [c for c in self.active_cycles if c.id != cycle.id]
        self.closed_cycles.append(cycle)
        return cycle
