from datetime import datetime

from notifications.models import Notification, NotificationLevel
from storage.database_manager import DatabaseManager


class NotificationEngine:
    """Центр повідомлень MVP.

    Повідомлення не замінюють system_events:
    - system_events — технічний журнал;
    - notifications — те, що треба показати користувачу.
    """

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def notify(
        self,
        level: NotificationLevel,
        title: str,
        message: str,
        cycle_id: int | None = None,
    ) -> int:
        notification = Notification(
            level=level,
            title=title,
            message=message,
            is_read=False,
            created_at=datetime.utcnow(),
            cycle_id=cycle_id,
        )
        return self.database.save_notification(notification)

    def info(self, title: str, message: str, cycle_id: int | None = None) -> int:
        return self.notify(NotificationLevel.INFO, title, message, cycle_id)

    def important(self, title: str, message: str, cycle_id: int | None = None) -> int:
        return self.notify(NotificationLevel.IMPORTANT, title, message, cycle_id)

    def warning(self, title: str, message: str, cycle_id: int | None = None) -> int:
        return self.notify(NotificationLevel.WARNING, title, message, cycle_id)

    def critical(self, title: str, message: str, cycle_id: int | None = None) -> int:
        return self.notify(NotificationLevel.CRITICAL, title, message, cycle_id)

    def get_unread_count(self) -> int:
        return self.database.count_unread_notifications()

    def mark_all_as_read(self) -> None:
        self.database.mark_all_notifications_as_read()
