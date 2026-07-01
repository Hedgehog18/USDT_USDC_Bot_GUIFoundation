from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from storage.database_manager import DatabaseManager


class PaperState(str, Enum):
    INIT = "INIT"
    READY = "READY"
    RUNNING = "RUNNING"
    SAFE_STOP = "SAFE_STOP"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PaperStateTransition:
    previous_state: PaperState
    new_state: PaperState
    reason: str
    created_at: datetime


class PaperStateManager:
    ALLOWED = {
        PaperState.INIT: {PaperState.READY, PaperState.ERROR},
        PaperState.READY: {PaperState.RUNNING, PaperState.STOPPED, PaperState.ERROR},
        PaperState.RUNNING: {
            PaperState.READY,
            PaperState.SAFE_STOP,
            PaperState.RECOVERY_REQUIRED,
            PaperState.STOPPED,
            PaperState.ERROR,
        },
        PaperState.SAFE_STOP: {PaperState.READY, PaperState.STOPPED, PaperState.ERROR},
        PaperState.RECOVERY_REQUIRED: {PaperState.READY, PaperState.STOPPED, PaperState.ERROR},
        PaperState.STOPPED: {PaperState.READY, PaperState.ERROR},
        PaperState.ERROR: {PaperState.READY, PaperState.STOPPED},
    }

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.current_state = PaperState.INIT

    def transition_to(self, new_state: PaperState, reason: str) -> PaperStateTransition:
        if new_state not in self.ALLOWED.get(self.current_state, set()):
            self.database.save_system_event("ERROR", "PaperStateManager", f"Invalid transition {self.current_state.value}->{new_state.value}: {reason}")
            raise RuntimeError(f"Invalid paper transition: {self.current_state.value}->{new_state.value}")

        transition = PaperStateTransition(self.current_state, new_state, reason, datetime.utcnow())
        self.database.save_paper_state_transition(transition)
        self.database.save_system_event("INFO", "PaperStateManager", f"Paper state {transition.previous_state.value}->{transition.new_state.value}: {reason}")
        self.current_state = new_state
        return transition
