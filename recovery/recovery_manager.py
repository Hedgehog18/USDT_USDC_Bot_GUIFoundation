from storage.database_manager import DatabaseManager
from trading.cycle_manager import CycleManager
from trading.models import Cycle


class RecoveryManager:
    def __init__(self, database: DatabaseManager, cycle_manager: CycleManager) -> None:
        self.database = database
        self.cycle_manager = cycle_manager

    def recover_active_cycles(self) -> list[Cycle]:
        active_cycles = self.database.load_active_cycles()

        for cycle in active_cycles:
            self.cycle_manager.add_recovered_cycle(cycle)

        self.database.save_system_event(
            level="INFO",
            module="RecoveryManager",
            message=f"Відновлено активних циклів: {len(active_cycles)}",
        )

        return active_cycles
