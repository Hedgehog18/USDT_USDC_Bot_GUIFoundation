from pathlib import Path

from paper.paper_safety_engine import PaperSafetyResult
from storage.database_manager import DatabaseManager


def test_database_saves_paper_safety_event(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    result = PaperSafetyResult(allowed=True, level="INFO", reason="ok")

    row_id = database.save_paper_safety_event(result, 100.0)

    assert row_id > 0
    assert database.count_rows("paper_safety_events") == 1
