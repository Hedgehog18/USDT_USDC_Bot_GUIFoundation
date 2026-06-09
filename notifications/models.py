from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class NotificationLevel(str, Enum):
    INFO = "INFO"
    IMPORTANT = "IMPORTANT"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Notification:
    level: NotificationLevel
    title: str
    message: str
    is_read: bool
    created_at: datetime
    cycle_id: int | None = None
