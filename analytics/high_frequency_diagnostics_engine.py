from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


TARGET_PERCENTS = (0.001, 0.0025, 0.005, 0.0075, 0.01)


@dataclass(frozen=True)
class HighFrequencyBlocker:
    name: str
    count: int
    rate: float


@dataclass(frozen=True)
class HighFrequencyScenarioResult:
    name: str
    description: str
    candidate_count: int
    candidate_rate: float
    buy_count: int
    sell_count: int
    top_blockers: list[HighFrequencyBlocker]


@dataclass(frozen=True)
class HighFrequencyTargetResult:
    target_percent: float
    candidate_count: int
    hit_count: int
    hit_rate: float
    average_holding_steps: float | None
    average_holding_seconds: float | None
    theoretical_cycles_per_hour: float
    theoretical_cycles_per_day: float


@dataclass(frozen=True)
class HighFrequencyDiagnosticsReport:
    total_samples: int
    sample_span_hours: float
    estimated_sample_interval_seconds: float
    current_candidate_count: int
    current_candidate_rate: float
    current_blockers: list[HighFrequencyBlocker]
    micro_entry_scenarios: list[HighFrequencyScenarioResult]
    target_results: list[HighFrequencyTargetResult]
    choking_filters: list[HighFrequencyBlocker]
    current_closed_cycles: int
    current_cycles_per_day: float
    potential_cycles_per_hour: float
    potential_cycles_per_day: float
    better_fit: str
    recommendation: str


class HighFrequencyDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(self) -> HighFrequencyDiagnosticsReport:
        rows = self._load_snapshot_rows()
        interval_seconds = self._estimated_interval_seconds(rows)
        span_hours = self._sample_span_hours(rows, interval_seconds)
        current_candidates, current_blockers = self._evaluate_current_strategy(rows)
        scenarios = self._build_micro_entry_scenarios(rows)
        hf_candidates = self._potential_high_frequency_candidates(rows)
        target_results = [
            self._evaluate_target(rows, hf_candidates, target_percent, interval_seconds, span_hours)
            for target_percent in TARGET_PERCENTS
        ]
        best_target = max(target_results, key=lambda item: (item.theoretical_cycles_per_day, item.hit_rate), default=None)
        closed_cycles, current_cycles_per_day = self._current_profile_cycle_rate()
        potential_cycles_per_day = best_target.theoretical_cycles_per_day if best_target else 0.0
        potential_cycles_per_hour = best_target.theoretical_cycles_per_hour if best_target else 0.0
        better_fit = (
            "Potential High Frequency"
            if potential_cycles_per_day > max(current_cycles_per_day * 3.0, current_cycles_per_day + 10.0)
            else "Current Mean Reversion"
        )

        return HighFrequencyDiagnosticsReport(
            total_samples=len(rows),
            sample_span_hours=span_hours,
            estimated_sample_interval_seconds=interval_seconds,
            current_candidate_count=len(current_candidates),
            current_candidate_rate=len(current_candidates) / len(rows) if rows else 0.0,
            current_blockers=self._blockers(current_blockers, len(rows)),
            micro_entry_scenarios=scenarios,
            target_results=target_results,
            choking_filters=self._blockers(current_blockers, len(rows)),
            current_closed_cycles=closed_cycles,
            current_cycles_per_day=current_cycles_per_day,
            potential_cycles_per_hour=potential_cycles_per_hour,
            potential_cycles_per_day=potential_cycles_per_day,
            better_fit=better_fit,
            recommendation=self._recommend(rows, target_results, scenarios, better_fit),
        )

    def _build_micro_entry_scenarios(self, rows: list[dict]) -> list[HighFrequencyScenarioResult]:
        definitions = (
            (
                "current_mean_reversion",
                "Current small-target entry zones with strict micro trend.",
                lambda row, index: self._current_direction(row),
                True,
            ),
            (
                "relaxed_entry_30_70",
                "Softer work_position zones, still requiring strict micro trend.",
                lambda row, index: self._zone_direction(row, 30.0, 70.0),
                True,
            ),
            (
                "relaxed_entry_40_60",
                "Very soft work_position zones, still requiring strict micro trend.",
                lambda row, index: self._zone_direction(row, 40.0, 60.0),
                True,
            ),
            (
                "micro_movement_only",
                "Ignore work_position; use last tick direction as the candidate direction.",
                self._micro_movement_direction,
                False,
            ),
            (
                "spread_only",
                "Count any safe, valid-spread sample as a possible micro-cycle opportunity.",
                lambda row, index: self._fallback_direction(row),
                False,
            ),
            (
                "short_term_mean_reversion",
                "Use only price versus short_center for mean reversion direction.",
                self._short_mean_reversion_direction,
                False,
            ),
        )
        return [
            self._evaluate_scenario(rows, name, description, direction_builder, require_micro_trend)
            for name, description, direction_builder, require_micro_trend in definitions
        ]

    def _evaluate_scenario(
        self,
        rows: list[dict],
        name: str,
        description: str,
        direction_builder,
        require_micro_trend: bool,
    ) -> HighFrequencyScenarioResult:
        blockers: Counter[str] = Counter()
        candidates: list[dict] = []

        for index, row in enumerate(rows):
            direction = direction_builder(row, index)
            failures = self._basic_failures(row)
            if direction is None:
                failures.append("entry_condition")
            elif require_micro_trend and not self._micro_trend_pass(direction, row["micro_trend"]):
                failures.append("micro_trend")

            if failures:
                blockers.update(failures)
                continue
            candidates.append({**row, "direction": direction})

        return HighFrequencyScenarioResult(
            name=name,
            description=description,
            candidate_count=len(candidates),
            candidate_rate=len(candidates) / len(rows) if rows else 0.0,
            buy_count=sum(1 for item in candidates if item["direction"] == "BUY"),
            sell_count=sum(1 for item in candidates if item["direction"] == "SELL"),
            top_blockers=self._blockers(blockers, len(rows)),
        )

    def _evaluate_current_strategy(self, rows: list[dict]) -> tuple[list[dict], Counter[str]]:
        blockers: Counter[str] = Counter()
        candidates = []
        for row in rows:
            direction = self._current_direction(row)
            failures = self._basic_failures(row)
            if direction is None:
                failures.append("entry_zone_work_position")
            elif not self._micro_trend_pass(direction, row["micro_trend"]):
                failures.append("micro_trend")

            if failures:
                blockers.update(failures)
                continue
            candidates.append({**row, "direction": direction})
        return candidates, blockers

    def _evaluate_target(
        self,
        rows: list[dict],
        candidates: list[dict],
        target_percent: float,
        interval_seconds: float,
        span_hours: float,
    ) -> HighFrequencyTargetResult:
        target_decimal = target_percent / 100.0
        hit_steps: list[int] = []
        row_by_index = {row["index"]: row for row in rows}

        for candidate in candidates:
            entry_price = candidate["price"]
            if entry_price <= 0:
                continue
            target_price = (
                entry_price * (1.0 + target_decimal)
                if candidate["direction"] == "BUY"
                else entry_price * (1.0 - target_decimal)
            )
            for step in range(1, 31):
                future = row_by_index.get(candidate["index"] + step)
                if future is None:
                    break
                if candidate["direction"] == "BUY" and future["price"] >= target_price:
                    hit_steps.append(step)
                    break
                if candidate["direction"] == "SELL" and future["price"] <= target_price:
                    hit_steps.append(step)
                    break

        hit_count = len(hit_steps)
        avg_steps = sum(hit_steps) / hit_count if hit_steps else None
        avg_seconds = avg_steps * interval_seconds if avg_steps is not None else None
        cycles_per_hour = hit_count / span_hours if span_hours > 0 else 0.0
        return HighFrequencyTargetResult(
            target_percent=target_percent,
            candidate_count=len(candidates),
            hit_count=hit_count,
            hit_rate=hit_count / len(candidates) if candidates else 0.0,
            average_holding_steps=avg_steps,
            average_holding_seconds=avg_seconds,
            theoretical_cycles_per_hour=cycles_per_hour,
            theoretical_cycles_per_day=cycles_per_hour * 24.0,
        )

    def _potential_high_frequency_candidates(self, rows: list[dict]) -> list[dict]:
        candidates = []
        for index, row in enumerate(rows):
            if self._basic_failures(row):
                continue
            direction = self._short_mean_reversion_direction(row, index) or self._micro_movement_direction(row, index)
            if direction is None:
                continue
            candidates.append({**row, "direction": direction})
        return candidates

    def _current_direction(self, row: dict) -> str | None:
        return self._zone_direction(row, 25.0, 75.0)

    @staticmethod
    def _zone_direction(row: dict, buy_threshold: float, sell_threshold: float) -> str | None:
        if row["work_position"] <= buy_threshold:
            return "BUY"
        if row["work_position"] >= sell_threshold:
            return "SELL"
        return None

    def _micro_movement_direction(self, row: dict, index: int) -> str | None:
        if index <= 0:
            return None
        previous_price = row.get("previous_price")
        if previous_price is None or previous_price <= 0 or row["price"] == previous_price:
            return None
        return "BUY" if row["price"] < previous_price else "SELL"

    @staticmethod
    def _fallback_direction(row: dict) -> str:
        return "BUY" if row["work_position"] <= 50.0 else "SELL"

    @staticmethod
    def _short_mean_reversion_direction(row: dict, index: int) -> str | None:
        short_center = row["short_center"]
        if short_center <= 0 or row["price"] == short_center:
            return None
        return "BUY" if row["price"] < short_center else "SELL"

    @staticmethod
    def _micro_trend_pass(direction: str, micro_trend: str) -> bool:
        if direction == "BUY":
            return micro_trend == "BUY_DOMINANT"
        if direction == "SELL":
            return micro_trend == "SELL_DOMINANT"
        return False

    def _basic_failures(self, row: dict) -> list[str]:
        failures = []
        if not (0.0 < row["spread"] <= self.config.max_allowed_spread):
            failures.append("spread")
        if (
            row["market_health_score"] < self.config.min_market_health_score
            or row["market_health_status"] == "UNHEALTHY"
        ):
            failures.append("safety_market_health")
        if row["market_regime"] == "ABNORMAL":
            failures.append("market_regime")
        if row["volatility_regime"] == "EXTREME":
            failures.append("volatility_regime")
        return failures

    def _load_snapshot_rows(self) -> list[dict]:
        hf_rows = self._load_hf_snapshot_rows()
        if hf_rows:
            return hf_rows

        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    price,
                    work_position,
                    short_center,
                    spread,
                    market_regime,
                    micro_trend,
                    volatility_regime,
                    market_health_score,
                    market_health_status
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        previous_price = None
        for index, row in enumerate(rows):
            (
                timestamp,
                price,
                work_position,
                short_center,
                spread,
                market_regime,
                micro_trend,
                volatility_regime,
                market_health_score,
                market_health_status,
            ) = row
            current_price = self._float(price)
            result.append({
                "index": index,
                "timestamp": clean_display_text(timestamp),
                "parsed_timestamp": self._parse_timestamp(timestamp),
                "price": current_price,
                "previous_price": previous_price,
                "work_position": self._float(work_position),
                "short_center": self._float(short_center),
                "spread": self._float(spread),
                "market_regime": self._text(market_regime),
                "micro_trend": self._text(micro_trend),
                "volatility_regime": self._text(volatility_regime),
                "market_health_score": self._float(market_health_score),
                "market_health_status": self._text(market_health_status),
            })
            previous_price = current_price
        return result

    def _load_hf_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    price,
                    work_position,
                    distance_to_short_center,
                    spread,
                    market_regime,
                    micro_trend,
                    volatility_regime
                FROM market_snapshots_hf
                ORDER BY timestamp ASC
                """
            ).fetchall()

        result = []
        previous_price = None
        for index, row in enumerate(rows):
            (
                timestamp,
                price,
                work_position,
                distance_to_short_center,
                spread,
                market_regime,
                micro_trend,
                volatility_regime,
            ) = row
            current_price = self._float(price)
            result.append({
                "index": index,
                "timestamp": clean_display_text(timestamp),
                "parsed_timestamp": self._parse_timestamp(timestamp),
                "price": current_price,
                "previous_price": previous_price,
                "work_position": self._float(work_position),
                "short_center": current_price - self._float(distance_to_short_center),
                "spread": self._float(spread),
                "market_regime": self._text(market_regime),
                "micro_trend": self._text(micro_trend),
                "volatility_regime": self._text(volatility_regime),
                "market_health_score": 100.0,
                "market_health_status": "HEALTHY",
            })
            previous_price = current_price
        return result

    def _current_profile_cycle_rate(self) -> tuple[int, float]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT opened_at, closed_at
                FROM paper_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'CLOSED_MANUAL')
                  AND closed_at IS NOT NULL
                ORDER BY opened_at ASC
                """,
                ("mean_reversion_v2_small_target",),
            ).fetchall()

        closed_cycles = len(rows)
        parsed = [
            self._parse_timestamp(value)
            for row in rows
            for value in row
            if self._parse_timestamp(value) is not None
        ]
        if closed_cycles == 0 or len(parsed) < 2:
            return closed_cycles, 0.0
        span_days = max((max(parsed) - min(parsed)).total_seconds() / 86400.0, 1 / 24)
        return closed_cycles, closed_cycles / span_days

    @staticmethod
    def _blockers(counter: Counter[str], total: int) -> list[HighFrequencyBlocker]:
        return [
            HighFrequencyBlocker(name=name, count=count, rate=count / total if total else 0.0)
            for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        ]

    @staticmethod
    def _estimated_interval_seconds(rows: list[dict]) -> float:
        timestamps = [row["parsed_timestamp"] for row in rows if row["parsed_timestamp"] is not None]
        deltas = [
            (right - left).total_seconds()
            for left, right in zip(timestamps, timestamps[1:])
            if (right - left).total_seconds() > 0
        ]
        return float(median(deltas)) if deltas else 60.0

    @staticmethod
    def _sample_span_hours(rows: list[dict], interval_seconds: float) -> float:
        timestamps = [row["parsed_timestamp"] for row in rows if row["parsed_timestamp"] is not None]
        if len(timestamps) >= 2:
            return max((max(timestamps) - min(timestamps)).total_seconds() / 3600.0, interval_seconds / 3600.0)
        return len(rows) * interval_seconds / 3600.0

    @staticmethod
    def _recommend(
        rows: list[dict],
        target_results: list[HighFrequencyTargetResult],
        scenarios: list[HighFrequencyScenarioResult],
        better_fit: str,
    ) -> str:
        if not rows:
            return "Collect market snapshots first; no high-frequency conclusion is possible."
        best_target = max(target_results, key=lambda item: item.theoretical_cycles_per_day, default=None)
        best_scenario = max(scenarios, key=lambda item: item.candidate_count, default=None)
        if better_fit == "Potential High Frequency" and best_target and best_target.hit_count > 0:
            return (
                f"Research micro-cycle rules around {best_scenario.name if best_scenario else 'micro entries'} "
                f"and targets near {best_target.target_percent:.4f}% before creating any runtime profile."
            )
        return "Current data does not yet show enough micro-cycle frequency; collect more live snapshots."

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        try:
            return datetime.fromisoformat(clean_display_text(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
