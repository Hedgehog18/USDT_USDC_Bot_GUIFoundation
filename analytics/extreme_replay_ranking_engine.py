from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

from analytics.extreme_replay_engine import ExtremeReplayEngine, ExtremeReplayReport
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class ExtremeReplayScenarioRanking:
    scenario_name: str
    events_count: int
    win_rate: float
    average_potential_profit: float | None
    median_potential_profit: float | None
    total_potential_profit: float
    average_mfe: float | None
    average_mae: float | None
    worst_mae: float | None
    average_reward_risk: float | None
    median_reward_risk: float | None
    best_event_contribution_share: float
    top3_event_contribution_share: float
    cluster_breakdown: dict[str, int]
    session_breakdown: dict[str, int]
    average_recovery_seconds: float | None
    median_recovery_seconds: float | None
    stability_score: float
    recommendation: str


@dataclass(frozen=True)
class ExtremeReplayRankingReport:
    profile: str
    scenario_rankings: list[ExtremeReplayScenarioRanking]
    best_scenario: ExtremeReplayScenarioRanking | None
    reason: str
    report_path: str


class ExtremeReplayRankingEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.replay_engine = ExtremeReplayEngine(database)

    def build_report(
        self,
        profile: str = "mean_reversion_hf_micro_v1",
        output_path: str | Path = "reports/extreme_replay_ranking.txt",
    ) -> ExtremeReplayRankingReport:
        replay_report = self.replay_engine.build_report(profile=profile)
        rankings = self.rank_replay_report(replay_report)
        best = rankings[0] if rankings else None
        report = ExtremeReplayRankingReport(
            profile=profile,
            scenario_rankings=rankings,
            best_scenario=best,
            reason=self._best_reason(best),
            report_path=str(output_path),
        )
        self._write_report(report, Path(output_path))
        return report

    def rank_replay_report(self, replay_report: ExtremeReplayReport) -> list[ExtremeReplayScenarioRanking]:
        by_scenario = defaultdict(list)
        for event in replay_report.events:
            for scenario in event.scenarios:
                if scenario.entered:
                    by_scenario[scenario.scenario].append((event, scenario))
        rankings = [
            self._rank_scenario(scenario_name, rows)
            for scenario_name, rows in by_scenario.items()
        ]
        return sorted(
            rankings,
            key=lambda item: (
                item.stability_score,
                item.median_potential_profit or 0.0,
                item.total_potential_profit,
            ),
            reverse=True,
        )

    def _rank_scenario(self, scenario_name: str, rows: list[tuple]) -> ExtremeReplayScenarioRanking:
        profits = [float(scenario.potential_profit or 0.0) for _event, scenario in rows]
        mfes = [float(scenario.maximum_favorable_excursion or 0.0) for _event, scenario in rows]
        maes = [float(scenario.maximum_adverse_excursion or 0.0) for _event, scenario in rows]
        reward_risks = [
            float(scenario.reward_risk)
            for _event, scenario in rows
            if scenario.reward_risk is not None
        ]
        recoveries = [
            float(scenario.recovery_seconds)
            for _event, scenario in rows
            if scenario.recovery_seconds is not None
        ]
        total_profit = sum(profits)
        cluster_breakdown = dict(Counter(event.cluster_label for event, _scenario in rows))
        session_breakdown = dict(Counter(event.session for event, _scenario in rows))
        best_share = self._top_share(profits, 1)
        top3_share = self._top_share(profits, 3)
        win_count = sum(
            1 for _event, scenario in rows
            if float(scenario.potential_profit or 0.0) > float(scenario.potential_loss or 0.0)
        )
        score = self._stability_score(
            events_count=len(rows),
            median_profit=median(profits) if profits else 0.0,
            average_profit=mean(profits) if profits else 0.0,
            worst_mae=max(maes) if maes else 0.0,
            best_share=best_share,
            top3_share=top3_share,
            cluster_breakdown=cluster_breakdown,
            session_breakdown=session_breakdown,
            average_reward_risk=mean(reward_risks) if reward_risks else None,
        )
        return ExtremeReplayScenarioRanking(
            scenario_name=scenario_name,
            events_count=len(rows),
            win_rate=(win_count / len(rows)) if rows else 0.0,
            average_potential_profit=mean(profits) if profits else None,
            median_potential_profit=median(profits) if profits else None,
            total_potential_profit=total_profit,
            average_mfe=mean(mfes) if mfes else None,
            average_mae=mean(maes) if maes else None,
            worst_mae=max(maes) if maes else None,
            average_reward_risk=mean(reward_risks) if reward_risks else None,
            median_reward_risk=median(reward_risks) if reward_risks else None,
            best_event_contribution_share=best_share,
            top3_event_contribution_share=top3_share,
            cluster_breakdown=cluster_breakdown,
            session_breakdown=session_breakdown,
            average_recovery_seconds=mean(recoveries) if recoveries else None,
            median_recovery_seconds=median(recoveries) if recoveries else None,
            stability_score=score,
            recommendation=self._recommendation(len(rows), score, top3_share, max(maes) if maes else 0.0),
        )

    def _stability_score(
        self,
        *,
        events_count: int,
        median_profit: float,
        average_profit: float,
        worst_mae: float,
        best_share: float,
        top3_share: float,
        cluster_breakdown: dict[str, int],
        session_breakdown: dict[str, int],
        average_reward_risk: float | None,
    ) -> float:
        if events_count == 0:
            return 0.0
        sample_score = min(events_count / 30.0, 1.0) * 20.0
        median_score = min(max(median_profit / 0.0005, 0.0), 2.0) * 15.0
        average_score = min(max(average_profit / 0.0005, 0.0), 2.0) * 10.0
        mae_penalty = min(max(worst_mae / 0.0001, 0.0), 3.0) * 10.0
        concentration_penalty = (best_share * 15.0) + (top3_share * 10.0)
        cluster_penalty = self._dominance_share(cluster_breakdown) * 8.0
        session_penalty = self._dominance_share(session_breakdown) * 7.0
        reward_score = min(max((average_reward_risk or 3.0) / 3.0, 0.0), 1.0) * 15.0
        score = (
            sample_score
            + median_score
            + average_score
            + reward_score
            - mae_penalty
            - concentration_penalty
            - cluster_penalty
            - session_penalty
            + 30.0
        )
        return max(0.0, round(score, 2))

    def _recommendation(
        self,
        events_count: int,
        stability_score: float,
        top3_share: float,
        worst_mae: float,
    ) -> str:
        if events_count == 0:
            return "REJECT"
        if events_count < 10:
            return "NEEDS_MORE_DATA"
        if top3_share > 0.75 or worst_mae > 0.00020:
            return "REJECT"
        if stability_score >= 65:
            return "STRONG_REPLAY_CANDIDATE"
        if stability_score >= 45:
            return "PROMISING"
        return "REJECT"

    def _best_reason(self, best: ExtremeReplayScenarioRanking | None) -> str:
        if best is None:
            return "No replay scenarios entered; more Extreme data is needed."
        reasons = [
            f"highest stability score ({best.stability_score:.2f})",
            f"median potential profit {self._fmt(best.median_potential_profit)}",
            f"worst MAE {self._fmt(best.worst_mae)}",
            f"top3 contribution share {best.top3_event_contribution_share * 100:.2f}%",
        ]
        return ", ".join(reasons) + "."

    def _top_share(self, profits: list[float], count: int) -> float:
        positive_total = sum(value for value in profits if value > 0)
        if positive_total <= 0:
            return 0.0
        return sum(sorted((value for value in profits if value > 0), reverse=True)[:count]) / positive_total

    def _dominance_share(self, values: dict[str, int]) -> float:
        total = sum(values.values())
        if total <= 0:
            return 0.0
        return max(values.values()) / total

    def _write_report(self, report: ExtremeReplayRankingReport, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "=== Extreme Replay Scenario Ranking ===",
            f"Profile: {report.profile}",
            f"Scenarios ranked: {len(report.scenario_rankings)}",
            "",
        ]
        for item in report.scenario_rankings:
            lines.extend([
                f"Scenario: {item.scenario_name}",
                f"- events count: {item.events_count}",
                f"- win rate: {item.win_rate * 100:.2f}%",
                f"- average potential profit: {self._fmt(item.average_potential_profit)}",
                f"- median potential profit: {self._fmt(item.median_potential_profit)}",
                f"- total potential profit: {item.total_potential_profit:.8f}",
                f"- average MFE: {self._fmt(item.average_mfe)}",
                f"- average MAE: {self._fmt(item.average_mae)}",
                f"- worst MAE: {self._fmt(item.worst_mae)}",
                f"- average reward/risk: {self._fmt(item.average_reward_risk)}",
                f"- median reward/risk: {self._fmt(item.median_reward_risk)}",
                f"- best event contribution share: {item.best_event_contribution_share * 100:.2f}%",
                f"- top 3 event contribution share: {item.top3_event_contribution_share * 100:.2f}%",
                f"- cluster breakdown: {self._format_counter(item.cluster_breakdown)}",
                f"- session breakdown: {self._format_counter(item.session_breakdown)}",
                f"- average recovery: {self._fmt_seconds(item.average_recovery_seconds)}",
                f"- median recovery: {self._fmt_seconds(item.median_recovery_seconds)}",
                f"- stability score: {item.stability_score:.2f}",
                f"- recommendation: {item.recommendation}",
                "",
            ])
        lines.extend([
            f"Best replay scenario: {report.best_scenario.scenario_name if report.best_scenario else 'N/A'}",
            f"Reason: {report.reason}",
        ])
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _format_counter(self, values: dict[str, int]) -> str:
        if not values:
            return "N/A"
        return ", ".join(f"{key}={count}" for key, count in sorted(values.items()))

    def _fmt(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.8f}"

    def _fmt_seconds(self, value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.0f}s"
