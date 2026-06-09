from pathlib import Path

from paper.paper_recovery_manager import PaperRecoveryManager
from paper.paper_state_manager import PaperState, PaperStateManager
from storage.database_manager import DatabaseManager


def test_paper_state_manager_valid_flow(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    manager = PaperStateManager(database)

    manager.transition_to(PaperState.READY, "ready")
    manager.transition_to(PaperState.RUNNING, "running")
    manager.transition_to(PaperState.READY, "done")

    assert manager.current_state == PaperState.READY
    assert database.count_rows("paper_state_transitions") == 3


def test_paper_recovery_empty_database(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    snapshot = PaperRecoveryManager(database).recover()

    assert snapshot.portfolio.total_value == 100.0
    assert snapshot.active_cycles == 0
    assert snapshot.last_cycle_status == "NONE"
