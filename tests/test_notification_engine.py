from pathlib import Path

from notifications.notification_engine import NotificationEngine
from storage.database_manager import DatabaseManager


def test_notification_engine_creates_unread_notification(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = NotificationEngine(database)

    engine.info("Test", "Message")

    assert database.count_rows("notifications") == 1
    assert engine.get_unread_count() == 1


def test_notification_engine_mark_all_as_read(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = NotificationEngine(database)

    engine.warning("Warning", "Message")
    engine.mark_all_as_read()

    assert engine.get_unread_count() == 0


def test_load_recent_notifications(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    engine = NotificationEngine(database)

    engine.important("One", "First")
    engine.critical("Two", "Second")

    notifications = database.load_recent_notifications()

    assert len(notifications) == 2
    assert notifications[0].title == "Two"
