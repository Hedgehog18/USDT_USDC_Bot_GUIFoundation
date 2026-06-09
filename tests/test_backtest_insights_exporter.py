from pathlib import Path

from backtest.backtest_insights_engine import BacktestInsights
from backtest.backtest_insights_exporter import BacktestInsightsExporter


def test_backtest_insights_exporter(tmp_path: Path):
    insights = BacktestInsights(
        rating="GOOD",
        summary="ok",
        strengths=["a"],
        weaknesses=[],
        warnings=[],
        next_steps=["b"],
    )

    path = BacktestInsightsExporter(str(tmp_path)).export_txt(1, insights)

    assert path.exists()
    assert "insights" in path.name
