from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT
from storage.database_manager import DatabaseManager


OUTCOME_EXECUTABLE_TARGET_TOUCH = "EXECUTABLE_TARGET_TOUCH"
OUTCOME_TIMEOUT_NO_TOUCH = "TIMEOUT_NO_TOUCH"
OUTCOME_HISTORICAL_ANOMALY = "HISTORICAL_EXECUTION_ANOMALY"

REPEATED_ENTRY_PRICE_PROXIMITY = Decimal("0.000005")
REPEATED_ENTRY_CENTER_PROXIMITY = Decimal("0.000005")
REPEATED_ENTRY_TARGET_PROXIMITY = Decimal("0.000005")
REPEATED_ENTRY_TIME_WINDOW_SECONDS = Decimal("900")

LOW_SAMPLE_SIZE_THRESHOLD = 10
VERY_LOW_DIRECTION_SAMPLE_THRESHOLD = 5


@dataclass(frozen=True)
class HFEntryOutcomeCycle:
    db_id: int
    outcome_group: str
    direction: str
    open_price: Decimal
    target_price: Decimal
    close_price: Decimal | None
    net_profit: Decimal
    close_reason: str | None
    opened_at: datetime | None
    closed_at: datetime | None
    holding_seconds: Decimal | None
    entry_spread: Decimal | None
    short_center: Decimal | None
    distance_from_center: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    movement_5s: Decimal | None
    movement_15s: Decimal | None
    movement_30s: Decimal | None
    movement_60s: Decimal | None
    immediate_adverse_movement: bool
    executable_target_touched: bool
    real_target_close_triggered: bool
    post_exit_target_touched: bool | None
    time_to_post_target: Decimal | None


@dataclass(frozen=True)
class HFEntryOutcomeGroupStats:
    name: str
    sample_size: int
    buy_count: int
    sell_count: int
    average_spread: Decimal | None
    median_spread: Decimal | None
    average_distance_from_center: Decimal | None
    median_distance_from_center: Decimal | None
    average_mfe: Decimal | None
    median_mfe: Decimal | None
    average_mae: Decimal | None
    median_mae: Decimal | None
    average_movement_5s: Decimal | None
    average_movement_15s: Decimal | None
    average_movement_30s: Decimal | None
    average_movement_60s: Decimal | None
    immediate_adverse_rate: Decimal
    average_holding_seconds: Decimal | None
    average_net_result: Decimal | None


@dataclass(frozen=True)
class HFEntryMovementBucket:
    interval_seconds: int
    group_name: str
    sample_size: int
    toward_target: int
    neutral: int
    against_target: int
    toward_rate: Decimal
    neutral_rate: Decimal
    against_rate: Decimal


@dataclass(frozen=True)
class HFEntryOutcomeComparisonDelta:
    label: str
    left_group: str
    right_group: str
    left_sample_size: int
    right_sample_size: int
    average_net_difference: Decimal | None
    median_mfe_difference: Decimal | None
    median_mae_difference: Decimal | None
    immediate_adverse_rate_difference: Decimal | None
    effect_direction: str


@dataclass(frozen=True)
class HFRepeatedEntryCluster:
    cluster_id: int
    cycle_ids: list[int]
    direction: str
    first_outcome: str
    repeated_outcomes: list[str]
    repeated_timeout_rate: Decimal


@dataclass(frozen=True)
class HFPostExitOutcomeStats:
    timeout_cycles_with_observer: int
    target_reached_after_timeout: int
    never_reached_after_timeout: int
    average_time_to_post_target: Decimal | None
    buy_timeout_cycles_with_observer: int
    buy_target_reached_after_timeout: int
    sell_timeout_cycles_with_observer: int
    sell_target_reached_after_timeout: int


@dataclass(frozen=True)
class HFEntryOutcomeComparisonReport:
    profile: str
    cycles_analyzed: int
    cycles_without_blackbox: int
    cycles_excluded_incomplete: int
    target_touch_group: HFEntryOutcomeGroupStats
    timeout_no_touch_group: HFEntryOutcomeGroupStats
    direction_group_stats: dict[str, dict[str, HFEntryOutcomeGroupStats]]
    comparisons: list[HFEntryOutcomeComparisonDelta]
    early_movement: list[HFEntryMovementBucket]
    repeated_entry_clusters: list[HFRepeatedEntryCluster]
    post_exit_outcomes: HFPostExitOutcomeStats
    historical_anomalies: list[HFEntryOutcomeCycle]
    cycle_table: list[HFEntryOutcomeCycle]
    warnings: list[str]
    recommendation: str
    research_conclusion: str

    def to_dict(self) -> dict[str, Any]:
        return _to_jsonable(self)


class HFEntryOutcomeComparisonEngine:
    OFFSETS_SECONDS = (5, 15, 30, 60)

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(
        self,
        profile: str = "mean_reversion_hf_micro_v1",
        *,
        direction: str | None = None,
    ) -> HFEntryOutcomeComparisonReport:
        main_cycles: list[HFEntryOutcomeCycle] = []
        anomalies: list[HFEntryOutcomeCycle] = []
        cycles_without_blackbox = 0
        cycles_excluded_incomplete = 0

        for cycle in self._load_real_cycles(profile):
            if direction is not None and str(cycle.get("direction")) != direction:
                continue
            snapshots = self.database.load_real_pilot_market_snapshots(int(cycle["id"]))
            if not snapshots:
                cycles_without_blackbox += 1
                continue
            built = self._build_cycle(cycle, snapshots)
            if built is None:
                cycles_excluded_incomplete += 1
                continue
            if built.db_id == 25:
                anomalies.append(_replace_outcome(built, OUTCOME_HISTORICAL_ANOMALY))
                continue
            if built.outcome_group in {OUTCOME_EXECUTABLE_TARGET_TOUCH, OUTCOME_TIMEOUT_NO_TOUCH}:
                main_cycles.append(built)

        target_cycles = [cycle for cycle in main_cycles if cycle.outcome_group == OUTCOME_EXECUTABLE_TARGET_TOUCH]
        timeout_cycles = [cycle for cycle in main_cycles if cycle.outcome_group == OUTCOME_TIMEOUT_NO_TOUCH]
        direction_group_stats = {
            outcome: {
                side: self._group_stats(f"{outcome}_{side}", [cycle for cycle in main_cycles if cycle.outcome_group == outcome and cycle.direction == side])
                for side in ("BUY_USDC", "SELL_USDC")
            }
            for outcome in (OUTCOME_EXECUTABLE_TARGET_TOUCH, OUTCOME_TIMEOUT_NO_TOUCH)
        }
        comparisons = [
            self._comparison("ALL", target_cycles, timeout_cycles),
            self._comparison("BUY_USDC", [c for c in target_cycles if c.direction == "BUY_USDC"], [c for c in timeout_cycles if c.direction == "BUY_USDC"]),
            self._comparison("SELL_USDC", [c for c in target_cycles if c.direction == "SELL_USDC"], [c for c in timeout_cycles if c.direction == "SELL_USDC"]),
        ]
        early_movement = [
            bucket
            for offset in self.OFFSETS_SECONDS
            for bucket in (
                self._movement_bucket(offset, OUTCOME_EXECUTABLE_TARGET_TOUCH, target_cycles),
                self._movement_bucket(offset, OUTCOME_TIMEOUT_NO_TOUCH, timeout_cycles),
            )
        ]
        clusters = self._repeated_entry_clusters(main_cycles)
        post_exit = self._post_exit_stats(timeout_cycles)
        warnings = self._warnings(target_cycles, timeout_cycles, direction_group_stats)
        recommendation = self._recommendation(target_cycles, timeout_cycles, clusters, comparisons, warnings)
        return HFEntryOutcomeComparisonReport(
            profile=profile,
            cycles_analyzed=len(main_cycles),
            cycles_without_blackbox=cycles_without_blackbox,
            cycles_excluded_incomplete=cycles_excluded_incomplete,
            target_touch_group=self._group_stats(OUTCOME_EXECUTABLE_TARGET_TOUCH, target_cycles),
            timeout_no_touch_group=self._group_stats(OUTCOME_TIMEOUT_NO_TOUCH, timeout_cycles),
            direction_group_stats=direction_group_stats,
            comparisons=comparisons,
            early_movement=early_movement,
            repeated_entry_clusters=clusters,
            post_exit_outcomes=post_exit,
            historical_anomalies=anomalies,
            cycle_table=main_cycles,
            warnings=warnings,
            recommendation=recommendation,
            research_conclusion=self._research_conclusion(recommendation, warnings),
        )

    def _build_cycle(self, cycle: dict[str, Any], snapshots: list[dict[str, Any]]) -> HFEntryOutcomeCycle | None:
        direction = str(cycle.get("direction") or "")
        open_price = _decimal(cycle.get("open_price"))
        if direction not in {"BUY_USDC", "SELL_USDC"} or open_price is None:
            return None
        target_price = _target_price(direction, open_price)
        opened_at = _parse_time(cycle.get("opened_at"))
        closed_at = _parse_time(cycle.get("closed_at"))
        path = [
            row for row in snapshots
            if row.get("phase") in {"entry", "tracking", "exit", "post_exit"}
            and _decimal(row.get("price")) is not None
        ]
        if not path:
            return None
        entry_snapshot = self._entry_snapshot(path, opened_at)
        entry_price = _decimal(entry_snapshot.get("price")) if entry_snapshot else open_price
        short_center = _decimal(entry_snapshot.get("short_center")) if entry_snapshot else None
        distance_from_center = (entry_price - short_center) if entry_price is not None and short_center is not None else None
        executable_target_touched = any(
            _target_hit(direction, executable, target_price)
            for executable in (_executable_close_reference(direction, row) for row in path)
            if executable is not None
        )
        real_target_close_triggered = str(cycle.get("close_reason") or "") == "real_pilot_target"
        is_timeout_no_touch = _is_timeout_reason(cycle.get("close_reason")) and not executable_target_touched
        if executable_target_touched:
            outcome = OUTCOME_EXECUTABLE_TARGET_TOUCH
        elif is_timeout_no_touch:
            outcome = OUTCOME_TIMEOUT_NO_TOUCH
        else:
            outcome = "EXCLUDED_OTHER"
        prices = [_decimal(row.get("price")) for row in path]
        prices = [price for price in prices if price is not None]
        movements = {
            offset: self._movement_after_entry(direction, entry_price, path, opened_at, offset)
            for offset in self.OFFSETS_SECONDS
        }
        first_movement = next((movements[offset] for offset in self.OFFSETS_SECONDS if movements[offset] is not None), None)
        post_exit = self.database.load_real_pilot_post_exit_summary(int(cycle["id"]))
        return HFEntryOutcomeCycle(
            db_id=int(cycle["id"]),
            outcome_group=outcome,
            direction=direction,
            open_price=open_price,
            target_price=target_price,
            close_price=_decimal(cycle.get("close_price")),
            net_profit=_decimal(cycle.get("net_profit")) or Decimal("0"),
            close_reason=str(cycle.get("close_reason")) if cycle.get("close_reason") else None,
            opened_at=opened_at,
            closed_at=closed_at,
            holding_seconds=_seconds_between(opened_at, closed_at),
            entry_spread=_decimal(entry_snapshot.get("spread")) if entry_snapshot else None,
            short_center=short_center,
            distance_from_center=distance_from_center,
            mfe=_mfe(direction, open_price, prices),
            mae=_mae(direction, open_price, prices),
            movement_5s=movements[5],
            movement_15s=movements[15],
            movement_30s=movements[30],
            movement_60s=movements[60],
            immediate_adverse_movement=first_movement is not None and first_movement < 0,
            executable_target_touched=executable_target_touched,
            real_target_close_triggered=real_target_close_triggered,
            post_exit_target_touched=_bool_or_none(post_exit.get("post_exit_target_touched")) if post_exit else None,
            time_to_post_target=_decimal(post_exit.get("time_to_post_target")) if post_exit else None,
        )

    def _load_real_cycles(self, profile: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, strategy_profile, symbol, direction, status,
                       open_price, close_price, quantity, stake_usdt, gross_profit,
                       net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
                FROM real_pilot_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'HALTED')
                ORDER BY id ASC
                """,
                (profile,),
            ).fetchall()
        keys = [
            "id", "timestamp", "strategy_profile", "symbol", "direction", "status",
            "open_price", "close_price", "quantity", "stake_usdt", "gross_profit",
            "net_profit", "opened_at", "closed_at", "close_reason", "exchange_order_id", "run_id",
        ]
        return [dict(zip(keys, row)) for row in rows]

    @staticmethod
    def _entry_snapshot(path: list[dict[str, Any]], opened_at: datetime | None) -> dict[str, Any] | None:
        entry = [row for row in path if row.get("phase") == "entry"]
        if entry:
            return entry[0]
        if opened_at is None:
            return path[0] if path else None
        return min(path, key=lambda row: abs(float(_seconds_between(opened_at, _parse_time(row.get("timestamp"))) or Decimal("0"))))

    @staticmethod
    def _movement_after_entry(
        direction: str,
        entry_price: Decimal | None,
        path: list[dict[str, Any]],
        opened_at: datetime | None,
        offset_seconds: int,
    ) -> Decimal | None:
        if entry_price is None or opened_at is None or not path:
            return None
        target_seconds = Decimal(str(offset_seconds))
        selected = min(
            path,
            key=lambda row: abs(_seconds_or_default(_seconds_between(opened_at, _parse_time(row.get("timestamp"))), target_seconds) - target_seconds),
        )
        price = _decimal(selected.get("price"))
        if price is None:
            return None
        return _pnl_per_unit(direction, entry_price, price)

    @staticmethod
    def _group_stats(name: str, cycles: list[HFEntryOutcomeCycle]) -> HFEntryOutcomeGroupStats:
        return HFEntryOutcomeGroupStats(
            name=name,
            sample_size=len(cycles),
            buy_count=sum(1 for cycle in cycles if cycle.direction == "BUY_USDC"),
            sell_count=sum(1 for cycle in cycles if cycle.direction == "SELL_USDC"),
            average_spread=_average(cycle.entry_spread for cycle in cycles),
            median_spread=_median(cycle.entry_spread for cycle in cycles),
            average_distance_from_center=_average(abs(cycle.distance_from_center) for cycle in cycles if cycle.distance_from_center is not None),
            median_distance_from_center=_median(abs(cycle.distance_from_center) for cycle in cycles if cycle.distance_from_center is not None),
            average_mfe=_average(cycle.mfe for cycle in cycles),
            median_mfe=_median(cycle.mfe for cycle in cycles),
            average_mae=_average(cycle.mae for cycle in cycles),
            median_mae=_median(cycle.mae for cycle in cycles),
            average_movement_5s=_average(cycle.movement_5s for cycle in cycles),
            average_movement_15s=_average(cycle.movement_15s for cycle in cycles),
            average_movement_30s=_average(cycle.movement_30s for cycle in cycles),
            average_movement_60s=_average(cycle.movement_60s for cycle in cycles),
            immediate_adverse_rate=_rate(sum(1 for cycle in cycles if cycle.immediate_adverse_movement), len(cycles)),
            average_holding_seconds=_average(cycle.holding_seconds for cycle in cycles),
            average_net_result=_average(cycle.net_profit for cycle in cycles),
        )

    @staticmethod
    def _movement_bucket(offset: int, group_name: str, cycles: list[HFEntryOutcomeCycle]) -> HFEntryMovementBucket:
        values = [getattr(cycle, f"movement_{offset}s") for cycle in cycles]
        values = [value for value in values if value is not None]
        toward = sum(1 for value in values if value > 0)
        neutral = sum(1 for value in values if value == 0)
        against = sum(1 for value in values if value < 0)
        return HFEntryMovementBucket(
            interval_seconds=offset,
            group_name=group_name,
            sample_size=len(values),
            toward_target=toward,
            neutral=neutral,
            against_target=against,
            toward_rate=_rate(toward, len(values)),
            neutral_rate=_rate(neutral, len(values)),
            against_rate=_rate(against, len(values)),
        )

    @staticmethod
    def _comparison(label: str, left: list[HFEntryOutcomeCycle], right: list[HFEntryOutcomeCycle]) -> HFEntryOutcomeComparisonDelta:
        left_stats = HFEntryOutcomeComparisonEngine._group_stats(f"{label}_target", left)
        right_stats = HFEntryOutcomeComparisonEngine._group_stats(f"{label}_timeout", right)
        average_net_difference = _difference(left_stats.average_net_result, right_stats.average_net_result)
        median_mfe_difference = _difference(left_stats.median_mfe, right_stats.median_mfe)
        median_mae_difference = _difference(left_stats.median_mae, right_stats.median_mae)
        adverse_difference = left_stats.immediate_adverse_rate - right_stats.immediate_adverse_rate
        return HFEntryOutcomeComparisonDelta(
            label=label,
            left_group=OUTCOME_EXECUTABLE_TARGET_TOUCH,
            right_group=OUTCOME_TIMEOUT_NO_TOUCH,
            left_sample_size=len(left),
            right_sample_size=len(right),
            average_net_difference=average_net_difference,
            median_mfe_difference=median_mfe_difference,
            median_mae_difference=median_mae_difference,
            immediate_adverse_rate_difference=adverse_difference,
            effect_direction=_effect_direction(average_net_difference),
        )

    @staticmethod
    def _repeated_entry_clusters(cycles: list[HFEntryOutcomeCycle]) -> list[HFRepeatedEntryCluster]:
        sorted_cycles = sorted(
            [cycle for cycle in cycles if cycle.opened_at is not None and cycle.short_center is not None],
            key=lambda cycle: cycle.opened_at or datetime.min.replace(tzinfo=timezone.utc),
        )
        clusters: list[list[HFEntryOutcomeCycle]] = []
        for cycle in sorted_cycles:
            placed = False
            for cluster in clusters:
                first = cluster[0]
                if _similar_entry(first, cycle):
                    cluster.append(cycle)
                    placed = True
                    break
            if not placed:
                clusters.append([cycle])
        result = []
        for index, cluster in enumerate([cluster for cluster in clusters if len(cluster) >= 2], start=1):
            repeated = cluster[1:]
            result.append(HFRepeatedEntryCluster(
                cluster_id=index,
                cycle_ids=[cycle.db_id for cycle in cluster],
                direction=cluster[0].direction,
                first_outcome=cluster[0].outcome_group,
                repeated_outcomes=[cycle.outcome_group for cycle in repeated],
                repeated_timeout_rate=_rate(sum(1 for cycle in repeated if cycle.outcome_group == OUTCOME_TIMEOUT_NO_TOUCH), len(repeated)),
            ))
        return result

    @staticmethod
    def _post_exit_stats(timeout_cycles: list[HFEntryOutcomeCycle]) -> HFPostExitOutcomeStats:
        with_observer = [cycle for cycle in timeout_cycles if cycle.post_exit_target_touched is not None]
        touched = [cycle for cycle in with_observer if cycle.post_exit_target_touched is True]
        buy = [cycle for cycle in with_observer if cycle.direction == "BUY_USDC"]
        sell = [cycle for cycle in with_observer if cycle.direction == "SELL_USDC"]
        return HFPostExitOutcomeStats(
            timeout_cycles_with_observer=len(with_observer),
            target_reached_after_timeout=len(touched),
            never_reached_after_timeout=sum(1 for cycle in with_observer if cycle.post_exit_target_touched is False),
            average_time_to_post_target=_average(cycle.time_to_post_target for cycle in touched),
            buy_timeout_cycles_with_observer=len(buy),
            buy_target_reached_after_timeout=sum(1 for cycle in buy if cycle.post_exit_target_touched is True),
            sell_timeout_cycles_with_observer=len(sell),
            sell_target_reached_after_timeout=sum(1 for cycle in sell if cycle.post_exit_target_touched is True),
        )

    @staticmethod
    def _warnings(
        target_cycles: list[HFEntryOutcomeCycle],
        timeout_cycles: list[HFEntryOutcomeCycle],
        direction_group_stats: dict[str, dict[str, HFEntryOutcomeGroupStats]],
    ) -> list[str]:
        warnings = []
        for name, cycles in ((OUTCOME_EXECUTABLE_TARGET_TOUCH, target_cycles), (OUTCOME_TIMEOUT_NO_TOUCH, timeout_cycles)):
            if len(cycles) < LOW_SAMPLE_SIZE_THRESHOLD:
                warnings.append(f"LOW_SAMPLE_SIZE:{name}:{len(cycles)}")
        for outcome, by_direction in direction_group_stats.items():
            for direction, stats in by_direction.items():
                if 0 < stats.sample_size < VERY_LOW_DIRECTION_SAMPLE_THRESHOLD:
                    warnings.append(f"VERY_LOW_SAMPLE_SIZE:{outcome}:{direction}:{stats.sample_size}")
        return warnings

    @staticmethod
    def _recommendation(
        target_cycles: list[HFEntryOutcomeCycle],
        timeout_cycles: list[HFEntryOutcomeCycle],
        clusters: list[HFRepeatedEntryCluster],
        comparisons: list[HFEntryOutcomeComparisonDelta],
        warnings: list[str],
    ) -> str:
        if len(target_cycles) < LOW_SAMPLE_SIZE_THRESHOLD or len(timeout_cycles) < LOW_SAMPLE_SIZE_THRESHOLD:
            return "CONTINUE_COLLECTING"
        all_comparison = next((comparison for comparison in comparisons if comparison.label == "ALL"), None)
        if all_comparison and all_comparison.immediate_adverse_rate_difference is not None:
            if all_comparison.immediate_adverse_rate_difference < Decimal("-0.25"):
                return "EARLY_ADVERSE_MOVE_REQUIRES_REVIEW"
        if clusters and any(cluster.repeated_timeout_rate >= Decimal("0.50") for cluster in clusters):
            return "REPEATED_ENTRY_REQUIRES_REVIEW"
        buy_timeout = sum(1 for cycle in timeout_cycles if cycle.direction == "BUY_USDC")
        sell_timeout = sum(1 for cycle in timeout_cycles if cycle.direction == "SELL_USDC")
        if abs(buy_timeout - sell_timeout) >= max(3, len(timeout_cycles) // 2):
            return "DIRECTION_ASYMMETRY_REQUIRES_REVIEW"
        if all_comparison and all_comparison.median_mfe_difference is not None and all_comparison.median_mfe_difference > Decimal("0.000010"):
            return "TARGET_DISTANCE_REQUIRES_REVIEW"
        return "NO_CLEAR_DIFFERENTIATOR"

    @staticmethod
    def _research_conclusion(recommendation: str, warnings: list[str]) -> str:
        if recommendation == "CONTINUE_COLLECTING":
            return "Sample is too small for a stable differentiator; keep collecting unchanged real-cycle data."
        if warnings:
            return "Potential differentiators are visible, but sample-size warnings require cautious interpretation."
        return "Comparison completed on stored data only; use the recommendation as research input, not a trading rule."


def _replace_outcome(cycle: HFEntryOutcomeCycle, outcome: str) -> HFEntryOutcomeCycle:
    return HFEntryOutcomeCycle(**{**cycle.__dict__, "outcome_group": outcome})


def _target_price(direction: str, open_price: Decimal) -> Decimal:
    target = Decimal(str(HF_MICRO_TARGET_PROFIT))
    if direction == "BUY_USDC":
        return open_price * (Decimal("1") + target)
    return open_price * (Decimal("1") - target)


def _target_hit(direction: str, price: Decimal, target_price: Decimal) -> bool:
    return price >= target_price if direction == "BUY_USDC" else price <= target_price


def _executable_close_reference(direction: str, snapshot: dict[str, Any]) -> Decimal | None:
    return _decimal(snapshot.get("bid")) if direction == "BUY_USDC" else _decimal(snapshot.get("ask"))


def _mfe(direction: str, open_price: Decimal, prices: list[Decimal]) -> Decimal | None:
    if not prices:
        return None
    best = max(prices) if direction == "BUY_USDC" else min(prices)
    return _pnl_per_unit(direction, open_price, best)


def _mae(direction: str, open_price: Decimal, prices: list[Decimal]) -> Decimal | None:
    if not prices:
        return None
    worst = min(prices) if direction == "BUY_USDC" else max(prices)
    return _pnl_per_unit(direction, open_price, worst)


def _pnl_per_unit(direction: str, open_price: Decimal, price: Decimal) -> Decimal:
    return price - open_price if direction == "BUY_USDC" else open_price - price


def _similar_entry(first: HFEntryOutcomeCycle, cycle: HFEntryOutcomeCycle) -> bool:
    if first.direction != cycle.direction:
        return False
    if first.short_center is None or cycle.short_center is None:
        return False
    if first.opened_at is None or cycle.opened_at is None:
        return False
    return (
        abs(first.open_price - cycle.open_price) <= REPEATED_ENTRY_PRICE_PROXIMITY
        and abs(first.short_center - cycle.short_center) <= REPEATED_ENTRY_CENTER_PROXIMITY
        and abs(first.target_price - cycle.target_price) <= REPEATED_ENTRY_TARGET_PROXIMITY
        and (_seconds_between(first.opened_at, cycle.opened_at) or Decimal("999999")) <= REPEATED_ENTRY_TIME_WINDOW_SECONDS
    )


def _is_timeout_reason(reason: Any) -> bool:
    text = str(reason or "")
    return "holding" in text or "timeout" in text


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        if isinstance(value, float):
            text = f"{value:.12f}".rstrip("0").rstrip(".")
            return Decimal(text or "0")
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _average(values: Any) -> Decimal | None:
    selected = [value for value in values if value is not None]
    if not selected:
        return None
    return sum(selected, Decimal("0")) / Decimal(len(selected))


def _median(values: Any) -> Decimal | None:
    selected = [value for value in values if value is not None]
    if not selected:
        return None
    return Decimal(str(median(selected)))


def _difference(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return left - right


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator)


def _effect_direction(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _seconds_between(start: datetime | None, end: datetime | None) -> Decimal | None:
    if start is None or end is None:
        return None
    return Decimal(str(max(0.0, (end - start).total_seconds())))


def _seconds_or_default(value: Decimal | None, default: Decimal) -> Decimal:
    return default if value is None else value


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_jsonable(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def report_to_json(report: HFEntryOutcomeComparisonReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)
