from pathlib import Path

from paper.paper_analytics_engine import PaperAnalytics
from paper.paper_report_exporter import PaperReportExporter


def test_paper_report_exporter(tmp_path: Path):
    exporter = PaperReportExporter(str(tmp_path))
    rows = [
        (
            "t", 1, "BUY_USDC", "CLOSED", 1.0, 1.01, 10.0, 0.01, 0.01, 0.1, 0.08, "target",
            1.01, 0.99, 0.1, -0.1, 0.0, 1, 1, 0.000005, 0.0, 0.1, 0.02, 0.8,
        )
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
    summary_path = exporter.export_summary_csv(stats, strategy_profile="mean_reversion_v1")

    assert cycles_path.exists()
    assert safety_path.exists()
    assert summary_path.exists()
    cycles_text = cycles_path.read_text(encoding="utf-8")
    assert "best_price_after_entry" in cycles_text
    assert "execution_quality_ratio" in cycles_text
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "strategy_profile" in summary_text
    assert "missed_target_count" in summary_text
    assert "worst_close_gap_to_target" in summary_text
    assert "mean_reversion_v1" in summary_text
