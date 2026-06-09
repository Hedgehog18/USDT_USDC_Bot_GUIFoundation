from storage.database_manager import DatabaseManager


def test_database_load_recent_system_events(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    database.save_system_event("INFO", "test", "message")

    rows = database.load_recent_system_events(limit=10)

    assert rows
    assert rows[0][1:] == ("INFO", "test", "message")
