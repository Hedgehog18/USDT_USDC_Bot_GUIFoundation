from pathlib import Path

from paper.paper_analytics_engine import PaperAnalytics
from paper.paper_report_exporter import PaperReportExporter


def test_paper_report_exporter(tmp_path: Path):
    exporter = PaperReportExporter(str(tmp_path))
    rows = [
        ("t", 1, "BUY_USDC", "CLOSED", 1.0, 1.01, 10.0, 0.01, 0.01, 0.1, 0.08)
    ]
    safety = [("t", "INFO", 1, "ok", 100.0)]
    stats = PaperAnalytics(
        total_cycles=1,
        closed_cycles=1,
        winning_cycles=1,
        losing_cycles=0,
        win_rate=1.0,
        gross_profit=0.1,
        net_profit=0.08,
        average_net_profit=0.08,
        profit_factor=0.08,
    )

    cycles_path = exporter.export_cycles_csv(rows)
    safety_path = exporter.export_safety_csv(safety)
    summary_path = exporter.export_summary_csv(stats)

    assert cycles_path.exists()
    assert safety_path.exists()
    assert summary_path.exists()
