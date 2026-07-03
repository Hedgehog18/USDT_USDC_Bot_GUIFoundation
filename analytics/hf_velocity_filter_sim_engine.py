from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean

from analytics.hf_extreme_price import is_extreme_close_price
from storage.database_manager import DatabaseManager


DEFAULT_VELOCITY_THRESHOLDS = (0.00001, 0.00002)
DEFAULT_DRIFT_THRESHOLDS = (0.00001, 0.00002)


@dataclass(frozen=True)
class HFVelocityCycle:
    db_id: int
    direction: str
    net_profit: float
    close_price: float
    close_reason: str
    opened_at: str | None
    closed_at: str | None
    current_price: float | None
    previous_price: float | None
    last_different_price: float | None
    short_center: float | None = None
    hf_entry_mode: str | None = None
    price_buffer_unique_values: int | None = None
    flat_samples_count: int | None = None
    flat_price_buffer: bool | None = None

    @property
    def price_velocity(self) -> float | None:
        if self.current_price is None or self.previous_price is None:
            return None
        return self.current_price - self.previous_price

    @property
    def short_term_drift(self) -> float | None:
        if self.current_price is None or self.last_different_price is None:
            return None
        return self.current_price - self.last_different_price

    @property
    def is_extreme(self) -> bool:
        return is_extreme_close_price(self.close_price)

    @property
    def is_timeout_loss(self) -> bool:
        reason = self.close_reason
        return (reason.startswith("max_holding_") or "timeout" in reason) and self.net_profit < 0

    @property
    def direction_confirmed(self) -> bool:
        velocity = self.price_velocity
        if velocity is None:
            return False
        return (self.direction == "BUY_USDC" and velocity > 0) or (
            self.direction == "SELL_USDC" and velocity < 0
        )

    @property
    def adverse_drift(self) -> bool:
        drift = self.short_term_drift
        if drift is None:
            return False
        return (self.direction == "BUY_USDC" and drift < 0) or (
            self.direction == "SELL_USDC" and drift > 0
        )


@dataclass(frozen=True)
class HFVelocityScenarioResult:
    scenario: str
    original_cycles: int
    original_non_extreme_cycles: int
    kept_cycles: int
    blocked_cycles: int
    blocked_winners: int
    blocked_losers: int
    kept_extreme_cycles: int
    blocked_extreme_cycles: int
    baseline_net_without_extreme: float
    net_kept_without_extreme: float
    net_blocked_without_extreme: float
    extreme_net_kept: float
    extreme_net_blocked: float
    win_rate_kept: float
    timeout_losses_kept: int
    timeout_losses_blocked: int
    average_net_kept: float
    net_improvement_vs_baseline: float
    cycles_per_day_estimate_after_filter: float
    recommendation: str


@dataclass(frozen=True)
class HFVelocityFilterSimulationReport:
    profile: str
    since_id: int
    limit: int | None
    cycles_count: int
    entry_context_available: int
    entry_context_missing: int
    baseline_net_without_extreme: float
    baseline_cycles_per_day: float
    scenarios: list[HFVelocityScenarioResult]


class HFVelocityFilterSimulationEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def simulate(
        self,
        *,
        profile: str,
        since_id: int = 0,
        velocity_threshold: float | None = None,
        drift_threshold: float | None = None,
        require_direction_confirmed: bool = False,
        limit: int | None = None,
    ) -> HFVelocityFilterSimulationReport:
        cycles = self._load_cycles(profile, since_id, limit)
        context_available = sum(1 for cycle in cycles if cycle.current_price is not None)
        baseline_net_without_extreme = self._net_without_extreme(cycles)
        baseline_cycles_per_day = self._cycles_per_day(cycles, len(cycles))

        scenarios: list[tuple[str, object]] = [
            ("baseline_no_filter", lambda cycle: False),
            ("block_unconfirmed_direction", lambda cycle: not cycle.direction_confirmed),
        ]
        for threshold in DEFAULT_VELOCITY_THRESHOLDS:
            scenarios.append((
                f"block_velocity_gt_{threshold:.5f}",
                lambda cycle, threshold=threshold: self._abs_gt(cycle.price_velocity, threshold),
            ))
        for threshold in DEFAULT_DRIFT_THRESHOLDS:
            scenarios.append((
                f"block_drift_gt_{threshold:.5f}",
                lambda cycle, threshold=threshold: self._abs_gt(cycle.short_term_drift, threshold),
            ))
        scenarios.append(("block_adverse_drift_only", lambda cycle: cycle.adverse_drift))
        combined_velocity = velocity_threshold if velocity_threshold is not None else DEFAULT_VELOCITY_THRESHOLDS[0]
        combined_drift = drift_threshold if drift_threshold is not None else DEFAULT_DRIFT_THRESHOLDS[0]
        scenarios.append((
            "combined_velocity_and_confirmation",
            lambda cycle: (
                not cycle.direction_confirmed
                or self._abs_gt(cycle.price_velocity, combined_velocity)
                or self._abs_gt(cycle.short_term_drift, combined_drift)
            ),
        ))
        if velocity_threshold is not None and velocity_threshold not in DEFAULT_VELOCITY_THRESHOLDS:
            scenarios.append((
                f"block_velocity_gt_custom_{velocity_threshold:.8f}",
                lambda cycle: self._abs_gt(cycle.price_velocity, velocity_threshold),
            ))
        if drift_threshold is not None and drift_threshold not in DEFAULT_DRIFT_THRESHOLDS:
            scenarios.append((
                f"block_drift_gt_custom_{drift_threshold:.8f}",
                lambda cycle: self._abs_gt(cycle.short_term_drift, drift_threshold),
            ))
        if require_direction_confirmed:
            scenarios.append((
                "custom_require_direction_confirmed",
                lambda cycle: not cycle.direction_confirmed,
            ))

        results = [
            self._scenario_result(name, cycles, should_block, baseline_net_without_extreme)
            for name, should_block in scenarios
        ]
        return HFVelocityFilterSimulationReport(
            profile=profile,
            since_id=since_id,
            limit=limit,
            cycles_count=len(cycles),
            entry_context_available=context_available,
            entry_context_missing=len(cycles) - context_available,
            baseline_net_without_extreme=baseline_net_without_extreme,
            baseline_cycles_per_day=baseline_cycles_per_day,
            scenarios=results,
        )

    def _scenario_result(
        self,
        name: str,
        cycles: list[HFVelocityCycle],
        should_block,
        baseline_net_without_extreme: float,
    ) -> HFVelocityScenarioResult:
        blocked = [cycle for cycle in cycles if should_block(cycle)]
        kept = [cycle for cycle in cycles if cycle not in blocked]
        kept_non_extreme = [cycle for cycle in kept if not cycle.is_extreme]
        blocked_non_extreme = [cycle for cycle in blocked if not cycle.is_extreme]
        net_kept = sum(cycle.net_profit for cycle in kept_non_extreme)
        net_blocked = sum(cycle.net_profit for cycle in blocked_non_extreme)
        win_rate_kept = (
            sum(1 for cycle in kept_non_extreme if cycle.net_profit > 0) / len(kept_non_extreme)
            if kept_non_extreme else 0.0
        )
        average_net_kept = mean([cycle.net_profit for cycle in kept_non_extreme]) if kept_non_extreme else 0.0
        improvement = net_kept - baseline_net_without_extreme
        return HFVelocityScenarioResult(
            scenario=name,
            original_cycles=len(cycles),
            original_non_extreme_cycles=sum(1 for cycle in cycles if not cycle.is_extreme),
            kept_cycles=len(kept),
            blocked_cycles=len(blocked),
            blocked_winners=sum(1 for cycle in blocked_non_extreme if cycle.net_profit > 0),
            blocked_losers=sum(1 for cycle in blocked_non_extreme if cycle.net_profit < 0),
            kept_extreme_cycles=sum(1 for cycle in kept if cycle.is_extreme),
            blocked_extreme_cycles=sum(1 for cycle in blocked if cycle.is_extreme),
            baseline_net_without_extreme=baseline_net_without_extreme,
            net_kept_without_extreme=net_kept,
            net_blocked_without_extreme=net_blocked,
            extreme_net_kept=sum(cycle.net_profit for cycle in kept if cycle.is_extreme),
            extreme_net_blocked=sum(cycle.net_profit for cycle in blocked if cycle.is_extreme),
            win_rate_kept=win_rate_kept,
            timeout_losses_kept=sum(1 for cycle in kept_non_extreme if cycle.is_timeout_loss),
            timeout_losses_blocked=sum(1 for cycle in blocked_non_extreme if cycle.is_timeout_loss),
            average_net_kept=average_net_kept,
            net_improvement_vs_baseline=improvement,
            cycles_per_day_estimate_after_filter=self._cycles_per_day(cycles, len(kept)),
            recommendation=self._recommendation(cycles, blocked_non_extreme, net_kept, baseline_net_without_extreme),
        )

    def _load_cycles(self, profile: str, since_id: int, limit: int | None) -> list[HFVelocityCycle]:
        limit_clause = "" if limit is None else "LIMIT ?"
        params: list[object] = [profile, since_id]
        if limit is not None:
            params.append(int(limit))
        with self.database.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    pc.id, pc.direction, pc.net_profit, pc.close_price,
                    pc.close_reason, pc.opened_at, pc.closed_at,
                    diag.current_price, diag.previous_price, diag.last_different_price,
                    diag.short_center, diag.hf_entry_mode,
                    diag.price_buffer_unique_values, diag.flat_samples_count,
                    diag.flat_price_buffer
                FROM paper_cycles pc
                LEFT JOIN hf_paper_cycle_entry_diagnostics diag
                    ON diag.paper_cycle_id = pc.id
                WHERE pc.strategy_profile = ?
                  AND pc.id > ?
                  AND pc.status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY pc.id ASC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return [
            HFVelocityCycle(
                db_id=int(row[0]),
                direction=str(row[1]),
                net_profit=float(row[2] or 0.0),
                close_price=float(row[3] or 0.0),
                close_reason=str(row[4] or ""),
                opened_at=row[5],
                closed_at=row[6],
                current_price=self._optional_float(row[7]),
                previous_price=self._optional_float(row[8]),
                last_different_price=self._optional_float(row[9]),
                short_center=self._optional_float(row[10]),
                hf_entry_mode=None if row[11] is None else str(row[11]),
                price_buffer_unique_values=self._optional_int(row[12]),
                flat_samples_count=self._optional_int(row[13]),
                flat_price_buffer=None if row[14] is None else bool(row[14]),
            )
            for row in rows
        ]

    def _cycles_per_day(self, cycles: list[HFVelocityCycle], count: int) -> float:
        duration = self._duration_seconds(cycles)
        return (count / (duration / 86400.0)) if duration and duration > 0 else 0.0

    def _duration_seconds(self, cycles: list[HFVelocityCycle]) -> float | None:
        times = []
        for cycle in cycles:
            for value in (cycle.opened_at, cycle.closed_at):
                parsed = self._parse_datetime(value)
                if parsed is not None:
                    times.append(parsed)
        if len(times) < 2:
            return None
        return max(0.0, (max(times) - min(times)).total_seconds())

    def _recommendation(
        self,
        cycles: list[HFVelocityCycle],
        blocked_non_extreme: list[HFVelocityCycle],
        net_kept: float,
        baseline_net_without_extreme: float,
    ) -> str:
        if not cycles or not blocked_non_extreme:
            return "DO_NOT_USE"
        blocked_winners = sum(1 for cycle in blocked_non_extreme if cycle.net_profit > 0)
        blocked_losers = sum(1 for cycle in blocked_non_extreme if cycle.net_profit < 0)
        cycles_per_day = self._cycles_per_day(cycles, len(cycles) - len(blocked_non_extreme))
        if blocked_losers > blocked_winners and net_kept > baseline_net_without_extreme and cycles_per_day >= 100:
            return "STRONG_FILTER_CANDIDATE"
        if blocked_losers > blocked_winners and net_kept > baseline_net_without_extreme:
            return "PROMISING_FILTER"
        return "DO_NOT_USE"

    def _net_without_extreme(self, cycles: list[HFVelocityCycle]) -> float:
        return sum(cycle.net_profit for cycle in cycles if not cycle.is_extreme)

    def _abs_gt(self, value: float | None, threshold: float) -> bool:
        if value is None:
            return False
        return abs(value) > threshold

    def _optional_float(self, value: object) -> float | None:
        if value is None:
            return None
        return float(value)

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def _parse_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
