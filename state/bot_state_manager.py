from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from storage.database_manager import DatabaseManager


class BotState(str, Enum):
    INIT = "INIT"
    RECOVERY = "RECOVERY"
    READY = "READY"
    RUNNING_DEMO = "RUNNING_DEMO"
    RUNNING_AUTO = "RUNNING_AUTO"
    SAFE_WAIT = "SAFE_WAIT"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class BotStateTransition:
    previous_state: BotState
    new_state: BotState
    reason: str
    created_at: datetime


class BotStateManager:
    """Керує формальним станом бота.

    MVP-версія:
    - фіксує поточний стан;
    - перевіряє базові переходи;
    - пише transition у system_events.
    """

    ALLOWED_TRANSITIONS = {
        BotState.INIT: {BotState.RECOVERY, BotState.ERROR},
        BotState.RECOVERY: {BotState.READY, BotState.SAFE_WAIT, BotState.ERROR},
        BotState.READY: {BotState.RUNNING_DEMO, BotState.RUNNING_AUTO, BotState.STOPPED, BotState.ERROR},
        BotState.RUNNING_DEMO: {BotState.READY, BotState.SAFE_WAIT, BotState.STOPPING, BotState.ERROR},
        BotState.RUNNING_AUTO: {BotState.READY, BotState.SAFE_WAIT, BotState.STOPPING, BotState.ERROR},
        BotState.SAFE_WAIT: {BotState.READY, BotState.STOPPING, BotState.ERROR},
        BotState.STOPPING: {BotState.STOPPED, BotState.ERROR},
        BotState.STOPPED: {BotState.READY, BotState.ERROR},
        BotState.ERROR: {BotState.RECOVERY, BotState.STOPPED},
    }

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.current_state = BotState.INIT

    def transition_to(self, new_state: BotState, reason: str) -> BotStateTransition:
        allowed = self.ALLOWED_TRANSITIONS.get(self.current_state, set())

        if new_state not in allowed:
            self.database.save_system_event(
                level="ERROR",
                module="BotStateManager",
                message=f"Недозволений перехід стану: {self.current_state.value} -> {new_state.value}. Причина: {reason}",
            )
            raise RuntimeError(f"Недозволений перехід стану: {self.current_state.value} -> {new_state.value}")

        transition = BotStateTransition(
            previous_state=self.current_state,
            new_state=new_state,
            reason=reason,
            created_at=datetime.utcnow(),
        )

        self.database.save_system_event(
            level="INFO",
            module="BotStateManager",
            message=f"Стан змінено: {transition.previous_state.value} -> {transition.new_state.value}. Причина: {reason}",
        )

        self.current_state = new_state
        return transition

    def can_run_demo(self) -> bool:
        return self.current_state == BotState.READY

    def can_run_auto(self) -> bool:
        return self.current_state == BotState.READY

    def is_safe_wait(self) -> bool:
        return self.current_state == BotState.SAFE_WAIT

    def is_error(self) -> bool:
        return self.current_state == BotState.ERROR
