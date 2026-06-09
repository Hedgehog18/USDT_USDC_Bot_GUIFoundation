from pathlib import Path

from backtest.backtest_insights_engine import BacktestInsights


class BacktestInsightsExporter:
    def __init__(self, reports_dir: str = "reports") -> None:
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def export_txt(self, run_id: int, insights: BacktestInsights) -> Path:
        path = self.reports_dir / f"backtest_run_{run_id}_insights.txt"

        lines = [
            f"Rating: {insights.rating}",
            f"Summary: {insights.summary}",
            "",
            "Strengths:",
            *[f"- {item}" for item in insights.strengths],
            "",
            "Weaknesses:",
            *[f"- {item}" for item in insights.weaknesses],
            "",
            "Warnings:",
            *[f"- {item}" for item in insights.warnings],
            "",
            "Next steps:",
            *[f"- {item}" for item in insights.next_steps],
            "",
        ]

        path.write_text("\n".join(lines), encoding="utf-8")
        return path
