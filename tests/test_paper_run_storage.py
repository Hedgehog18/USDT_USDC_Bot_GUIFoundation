from pathlib import Path

from paper.models import PaperPortfolio
from paper.paper_insights_engine import PaperInsights
from paper.paper_trading_engine import PaperTradingRunResult
from storage.database_manager import DatabaseManager


def test_database_saves_paper_run(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    result = PaperTradingRunResult(
        iterations=5,
        opened_cycles=1,
        closed_cycles=1,
        safety_stops=0,
        final_portfolio=PaperPortfolio(50.0, 50.0),
    )
    insights = PaperInsights("GOOD", "ok", [], [], [], [])
    run_id = database.save_paper_run(result, insights)

    assert run_id > 0
    assert database.count_rows("paper_runs") == 1
