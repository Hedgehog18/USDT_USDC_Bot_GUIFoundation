from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from analytics.hf_post_exit_observer import HFPostExitObserver
from analytics.hf_real_entry_quality_engine import HFRealEntryQualityDiagnosticsEngine
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager


TIME_BUCKETS_SECONDS = (30, 60, 120, 180, 300)


@dataclass(frozen=True)
class PostExitMetricStats:
    average: float | None
    median: float | None
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True)
class PostExitDirectionStats:
    direction: str
    timeout_cycles: int
    late_target_touch_count: int
    never_reached_count: int
    late_target_touch_rate: float
    average_time_to_target: float | None


@dataclass(frozen=True)
class PostExitCategoryStats:
    category: str
    cycles_count: int
    post_exit_target_touch_count: int
    average_mfe: float | None
    average_mae: float | None


@dataclass(frozen=True)
class PostExitObserverStatisticsReport:
    profile: str
    completed_observer_records: int
    timeout_cycles: int
    target_cycles: int
    timeout_reached_after_exit: int
    timeout_never_reached: int
    late_target_touch_rate: float
    time_to_target_stats: PostExitMetricStats
    time_buckets: dict[int, int]
    mfe_stats: PostExitMetricStats
    mae_stats: PostExitMetricStats
    closest_distance_stats: PostExitMetricStats
    direction_stats: list[PostExitDirectionStats]
    category_stats: list[PostExitCategoryStats]
    recommendation: str
    conclusion: str


@dataclass(frozen=True)
class _ObservedCycle:
    db_id: int
    direction: str
    close_reason: str
    post_exit_target_touched: bool | None
    time_to_post_target: float | None
    post_exit_mfe: float | None
    post_exit_mae: float | None
    closest_distance_after_exit: float | None
    category: str

    @property
    def is_timeout(self) -> bool:
        reason = self.close_reason.lower()
        return "holding" in reason or "timeout" in reason

    @property
    def is_target(self) -> bool:
        return self.close_reason == "real_pilot_target"


class HFPostExitObserverStatisticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config

    def build_report(self, profile: str = "mean_reversion_hf_micro_v1") -> PostExitObserverStatisticsReport:
        categories = {
            cycle.db_id: cycle.entry_quality_category
            for cycle in HFRealEntryQualityDiagnosticsEngine(self.database).build_report(profile).cycles
        }
        observer = HFPostExitObserver(self.database, self.config)
        cycles: list[_ObservedCycle] = []
        for cycle, summary in self._load_observer_records(profile):
            snapshots = self.database.load_real_pilot_post_exit_snapshots(int(cycle["id"]))
            recalculated = None
            if snapshots:
                recalculated = observer.calculate_result(
                    cycle,
                    snapshots,
                    duration_seconds=summary.get("duration_seconds"),
                    interval_seconds=summary.get("interval_seconds"),
                    status=str(summary.get("status") or "COMPLETED"),
                    error=summary.get("error"),
                )
            cycles.append(_ObservedCycle(
                db_id=int(cycle["id"]),
                direction=str(cycle["direction"]),
                close_reason=str(cycle.get("close_reason") or ""),
                post_exit_target_touched=(
                    recalculated.post_exit_target_touched
                    if recalculated is not None
                    else _bool_or_none(summary.get("post_exit_target_touched"))
                ),
                time_to_post_target=(
                    recalculated.time_to_post_target
                    if recalculated is not None
                    else _float_or_none(summary.get("time_to_post_target"))
                ),
                post_exit_mfe=(
                    recalculated.post_exit_mfe
                    if recalculated is not None
                    else _float_or_none(summary.get("post_exit_mfe"))
                ),
                post_exit_mae=(
                    recalculated.post_exit_mae
                    if recalculated is not None
                    else _float_or_none(summary.get("post_exit_mae"))
                ),
                closest_distance_after_exit=(
                    recalculated.closest_distance_after_exit
                    if recalculated is not None
                    else _float_or_none(summary.get("closest_distance_after_exit"))
                ),
                category=categories.get(int(cycle["id"]), "insufficient_data"),
            ))

        timeout_cycles = [cycle for cycle in cycles if cycle.is_timeout]
        target_cycles = [cycle for cycle in cycles if cycle.is_target]
        late_touch = [cycle for cycle in timeout_cycles if cycle.post_exit_target_touched is True]
        never_reached = [cycle for cycle in timeout_cycles if cycle.post_exit_target_touched is False]
        touch_rate = len(late_touch) / len(timeout_cycles) if timeout_cycles else 0.0
        times = [cycle.time_to_post_target for cycle in late_touch if cycle.time_to_post_target is not None]
        return PostExitObserverStatisticsReport(
            profile=profile,
            completed_observer_records=len(cycles),
            timeout_cycles=len(timeout_cycles),
            target_cycles=len(target_cycles),
            timeout_reached_after_exit=len(late_touch),
            timeout_never_reached=len(never_reached),
            late_target_touch_rate=touch_rate,
            time_to_target_stats=_stats(times),
            time_buckets={bucket: sum(1 for value in times if value <= bucket) for bucket in TIME_BUCKETS_SECONDS},
            mfe_stats=_stats(cycle.post_exit_mfe for cycle in cycles),
            mae_stats=_stats(cycle.post_exit_mae for cycle in cycles),
            closest_distance_stats=_stats(cycle.closest_distance_after_exit for cycle in cycles),
            direction_stats=self._direction_stats(timeout_cycles),
            category_stats=self._category_stats(cycles),
            recommendation=self._recommendation(touch_rate, times, len(timeout_cycles)),
            conclusion=self._conclusion(touch_rate, times, len(timeout_cycles)),
        )

    def _load_observer_records(self, profile: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id, c.timestamp, c.strategy_profile, c.symbol, c.direction,
                    c.status, c.open_price, c.close_price, c.quantity, c.stake_usdt,
                    c.gross_profit, c.net_profit, c.opened_at, c.closed_at,
                    c.close_reason, c.exchange_order_id, c.run_id,
                    s.real_cycle_id, s.campaign_id, s.started_at, s.finished_at,
                    s.duration_seconds, s.interval_seconds, s.snapshots_count,
                    s.post_exit_mfe, s.post_exit_mae, s.max_price, s.min_price,
                    s.post_exit_target_touched, s.time_to_post_target,
                    s.closest_distance_after_exit, s.status, s.error
                FROM real_pilot_post_exit_observer_summaries s
                JOIN real_pilot_cycles c ON c.id = s.real_cycle_id
                WHERE c.strategy_profile = ?
                  AND c.status IN ('CLOSED', 'HALTED')
                  AND s.status = 'COMPLETED'
                ORDER BY c.id ASC
                """,
                (profile,),
            ).fetchall()
        cycle_keys = [
            "id", "timestamp", "strategy_profile", "symbol", "direction",
            "status", "open_price", "close_price", "quantity", "stake_usdt",
            "gross_profit", "net_profit", "opened_at", "closed_at",
            "close_reason", "exchange_order_id", "run_id",
        ]
        summary_keys = [
            "real_cycle_id", "campaign_id", "started_at", "finished_at",
            "duration_seconds", "interval_seconds", "snapshots_count",
            "post_exit_mfe", "post_exit_mae", "max_price", "min_price",
            "post_exit_target_touched", "time_to_post_target",
            "closest_distance_after_exit", "status", "error",
        ]
        return [
            (dict(zip(cycle_keys, row[:len(cycle_keys)])), dict(zip(summary_keys, row[len(cycle_keys):])))
            for row in rows
        ]

    @staticmethod
    def _direction_stats(cycles: list[_ObservedCycle]) -> list[PostExitDirectionStats]:
        rows: list[PostExitDirectionStats] = []
        for direction in ("BUY_USDC", "SELL_USDC"):
            selected = [cycle for cycle in cycles if cycle.direction == direction]
            touched = [cycle for cycle in selected if cycle.post_exit_target_touched is True]
            times = [cycle.time_to_post_target for cycle in touched if cycle.time_to_post_target is not None]
            rows.append(PostExitDirectionStats(
                direction=direction,
                timeout_cycles=len(selected),
                late_target_touch_count=len(touched),
                never_reached_count=sum(1 for cycle in selected if cycle.post_exit_target_touched is False),
                late_target_touch_rate=(len(touched) / len(selected)) if selected else 0.0,
                average_time_to_target=mean(times) if times else None,
            ))
        return rows

    @staticmethod
    def _category_stats(cycles: list[_ObservedCycle]) -> list[PostExitCategoryStats]:
        categories = sorted({cycle.category for cycle in cycles} | {
            "good_entry_follow_through",
            "immediate_adverse_move",
            "spread_too_large",
        })
        rows = []
        for category in categories:
            selected = [cycle for cycle in cycles if cycle.category == category]
            if not selected:
                rows.append(PostExitCategoryStats(category, 0, 0, None, None))
                continue
            rows.append(PostExitCategoryStats(
                category=category,
                cycles_count=len(selected),
                post_exit_target_touch_count=sum(1 for cycle in selected if cycle.post_exit_target_touched is True),
                average_mfe=_average(cycle.post_exit_mfe for cycle in selected),
                average_mae=_average(cycle.post_exit_mae for cycle in selected),
            ))
        return rows

    @staticmethod
    def _recommendation(touch_rate: float, times: list[float], timeout_count: int) -> str:
        if timeout_count < 10:
            return "NEED_MORE_DATA"
        average_time = mean(times) if times else None
        if touch_rate >= 0.5 and average_time is not None and average_time <= 90:
            return "TIMEOUT_POLICY_DESERVES_INVESTIGATION"
        if touch_rate <= 0.2:
            return "CURRENT_TIMEOUT_PROBABLY_ACCEPTABLE"
        return "CONTINUE_COLLECTING"

    @staticmethod
    def _conclusion(touch_rate: float, times: list[float], timeout_count: int) -> str:
        if timeout_count == 0:
            return "No timeout cycles with completed Post Exit Observer data yet."
        average_time = mean(times) if times else None
        if touch_rate >= 0.5 and average_time is not None and average_time <= 90:
            return "Many timeout cycles still reach target shortly after exit; timeout policy deserves further research."
        if touch_rate <= 0.2:
            return "Late target touch rate is low; current timeout looks probably acceptable on available data."
        return "Timeout outcomes are mixed; collect more real cycles before changing any policy."


def _stats(values) -> PostExitMetricStats:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return PostExitMetricStats(None, None, None, None)
    return PostExitMetricStats(
        average=mean(clean),
        median=median(clean),
        minimum=min(clean),
        maximum=max(clean),
    )


def _average(values) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
