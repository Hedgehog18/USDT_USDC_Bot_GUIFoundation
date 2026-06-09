from paper.paper_analytics_engine import PaperAnalytics
from paper.paper_insights_engine import PaperInsights, PaperInsightsEngine
from paper.paper_insights_exporter import PaperInsightsExporter


def test_paper_insights_good():
    stats = PaperAnalytics(30, 30, 20, 10, 0.67, 2.0, 1.5, 0.05, 2.0)
    insights = PaperInsightsEngine().build(stats, [])
    assert insights.rating == "GOOD"


def test_paper_insights_no_closed_cycles():
    stats = PaperAnalytics(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    insights = PaperInsightsEngine().build(stats, [])
    assert insights.rating == "NO_CLOSED_CYCLES"


def test_paper_insights_exporter(tmp_path):
    insights = PaperInsights("GOOD", "ok", ["s"], [], [], ["n"])
    path = PaperInsightsExporter(str(tmp_path)).export_txt(1, insights)
    assert path.exists()
