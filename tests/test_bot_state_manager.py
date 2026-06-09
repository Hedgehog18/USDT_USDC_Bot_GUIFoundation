from pathlib import Path

import pytest

from state.bot_state_manager import BotState, BotStateManager
from storage.database_manager import DatabaseManager


def test_state_manager_valid_startup_flow(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    manager = BotStateManager(database)

    assert manager.current_state == BotState.INIT

    manager.transition_to(BotState.RECOVERY, "test recovery")
    manager.transition_to(BotState.READY, "test ready")
    manager.transition_to(BotState.RUNNING_DEMO, "test demo")
    manager.transition_to(BotState.READY, "demo done")

    assert manager.current_state == BotState.READY
    assert database.count_rows("system_events") == 4


def test_state_manager_blocks_invalid_transition(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    manager = BotStateManager(database)

    with pytest.raises(RuntimeError):
        manager.transition_to(BotState.RUNNING_DEMO, "invalid")
