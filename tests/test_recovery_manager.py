from pathlib import Path

from recovery.recovery_manager import RecoveryManager
from storage.database_manager import DatabaseManager
from trading.cycle_manager import CycleManager


def test_recovery_loads_active_cycle(tmp_path: Path):
    db_path = tmp_path / "bot.sqlite"
    database = DatabaseManager(str(db_path))

    original_manager = CycleManager()
    cycle = original_manager.create_cycle("DEMO", "BUY_USDC", 1.0, 10.0, 0.0002)
    original_manager.place_open_order(cycle)
    database.save_cycle(cycle)

    recovered_manager = CycleManager()
    recovery = RecoveryManager(database, recovered_manager)
    recovered = recovery.recover_active_cycles()

    assert len(recovered) == 1
    assert len(recovered_manager.active_cycles) == 1
