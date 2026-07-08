from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from analytics.hf_real_blackbox_engine import HFRealBlackboxDiagnosticsEngine
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFRealEntryCycleQuality:
    db_id: int
    campaign_id: str
    direction: str
    open_price: float
    target_price: float
    close_price: float | None
    net_profit: float
    close_reason: str | None
    target_touched: bool
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    nearest_target_distance: float | None
    first_target_touch_seconds: float | None
    entry_market_price: float | None
    entry_execution_gap: float | None
    entry_spread: float | None
    short_center_at_entry: float | None
    distance_from_short_center: float | None
    candidate_at_entry: bool | None
    block_reason_at_entry: str | None
    movement_after_5s: float | None
    movement_after_15s: float | None
    movement_after_30s: float | None
    movement_after_60s: float | None
    moved_expected_5s: bool | None
    moved_expected_15s: bool | None
    moved_expected_30s: bool | None
    moved_expected_60s: bool | None
    entry_quality_category: str
    has_blackbox: bool


@dataclass(frozen=True)
class HFRealEntryGroupMetrics:
    count: int
    average_distance_from_center: float | None
    average_entry_spread: float | None
    average_mfe: float | None
    average_mae: float | None
    average_movement_5s: float | None
    average_movement_15s: float | None
    average_movement_30s: float | None
    average_movement_60s: float | None
    target_touch_rate: float
    timeout_loss_rate: float
    buy_count: int
    sell_count: int


@dataclass(frozen=True)
class HFRealEntryQualityReport:
    profile: str
    cycles: list[HFRealEntryCycleQuality]
    cycles_without_blackbox: int
    total_analyzed_cycles: int
    cycles_with_blackbox: int
    target_touched_count: int
    timeout_no_touch_count: int
    timeout_loss_count: int
    breakeven_count: int
    target_metrics: HFRealEntryGroupMetrics
    timeout_metrics: HFRealEntryGroupMetrics
    category_counts: dict[str, int]
    main_issue: str
    recommendation: str


class HFRealEntryQualityDiagnosticsEngine:
    OFFSETS_SECONDS = (5, 15, 30, 60)

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, profile: str = "mean_reversion_hf_micro_v1") -> HFRealEntryQualityReport:
        cycles: list[HFRealEntryCycleQuality] = []
        cycles_without_blackbox = 0
        for cycle in self._load_real_cycles(profile):
            snapshots = self.database.load_real_pilot_market_snapshots(int(cycle["id"]))
            if not snapshots:
                cycles_without_blackbox += 1
                continue
            cycles.append(self._build_cycle(cycle, snapshots))

        target_cycles = [cycle for cycle in cycles if str(cycle.close_reason or "") == "real_pilot_target"]
        timeout_cycles = [cycle for cycle in cycles if self._is_timeout_reason(cycle.close_reason)]
        target_touched_count = sum(1 for cycle in cycles if cycle.target_touched)
        timeout_no_touch_count = sum(1 for cycle in timeout_cycles if not cycle.target_touched)
        timeout_loss_count = sum(1 for cycle in timeout_cycles if cycle.net_profit < 0)
        breakeven_count = sum(1 for cycle in cycles if abs(cycle.net_profit) <= 1e-12)
        category_counts: dict[str, int] = {}
        for cycle in cycles:
            category_counts[cycle.entry_quality_category] = category_counts.get(cycle.entry_quality_category, 0) + 1
        main_issue = self._main_issue(cycles, timeout_no_touch_count, timeout_loss_count, cycles_without_blackbox)
        return HFRealEntryQualityReport(
            profile=profile,
            cycles=cycles,
            cycles_without_blackbox=cycles_without_blackbox,
            total_analyzed_cycles=len(cycles) + cycles_without_blackbox,
            cycles_with_blackbox=len(cycles),
            target_touched_count=target_touched_count,
            timeout_no_touch_count=timeout_no_touch_count,
            timeout_loss_count=timeout_loss_count,
            breakeven_count=breakeven_count,
            target_metrics=self._group_metrics(target_cycles),
            timeout_metrics=self._group_metrics(timeout_cycles),
            category_counts=category_counts,
            main_issue=main_issue,
            recommendation=self._recommendation(cycles, main_issue, cycles_without_blackbox),
        )

    def _build_cycle(self, cycle: dict[str, Any], snapshots: list[dict[str, Any]]) -> HFRealEntryCycleQuality:
        direction = str(cycle["direction"])
        open_price = float(cycle["open_price"])
        target_price = HFRealBlackboxDiagnosticsEngine.target_price(direction, open_price)
        metrics = HFRealBlackboxDiagnosticsEngine.calculate_metrics(cycle, snapshots)
        opened_at = _parse_time(cycle.get("opened_at"))
        entry_snapshot = self._entry_snapshot(snapshots, opened_at)
        entry_price = _float(entry_snapshot.get("price")) if entry_snapshot else None
        short_center = _float(entry_snapshot.get("short_center")) if entry_snapshot else None
        movements = {
            offset: self._movement_after_entry(direction, entry_price, snapshots, opened_at, offset)
            for offset in self.OFFSETS_SECONDS
        }
        category = self._category(
            cycle=cycle,
            metrics=metrics,
            entry_spread=_float(entry_snapshot.get("spread")) if entry_snapshot else None,
            movements=movements,
            distance_from_center=(entry_price - short_center) if entry_price is not None and short_center is not None else None,
        )
        return HFRealEntryCycleQuality(
            db_id=int(cycle["id"]),
            campaign_id=self._campaign_id(cycle),
            direction=direction,
            open_price=open_price,
            target_price=target_price,
            close_price=_float(cycle.get("close_price")),
            net_profit=float(cycle.get("net_profit") or 0.0),
            close_reason=cycle.get("close_reason"),
            target_touched=metrics.target_touched,
            max_favorable_excursion=metrics.max_favorable_excursion,
            max_adverse_excursion=metrics.max_adverse_excursion,
            nearest_target_distance=metrics.nearest_target_distance,
            first_target_touch_seconds=metrics.first_target_touch_seconds,
            entry_market_price=metrics.entry_market_price,
            entry_execution_gap=metrics.entry_execution_gap,
            entry_spread=_float(entry_snapshot.get("spread")) if entry_snapshot else None,
            short_center_at_entry=short_center,
            distance_from_short_center=(entry_price - short_center) if entry_price is not None and short_center is not None else None,
            candidate_at_entry=_bool(entry_snapshot.get("candidate")) if entry_snapshot else None,
            block_reason_at_entry=entry_snapshot.get("block_reason") if entry_snapshot else None,
            movement_after_5s=movements[5],
            movement_after_15s=movements[15],
            movement_after_30s=movements[30],
            movement_after_60s=movements[60],
            moved_expected_5s=_positive_bool(movements[5]),
            moved_expected_15s=_positive_bool(movements[15]),
            moved_expected_30s=_positive_bool(movements[30]),
            moved_expected_60s=_positive_bool(movements[60]),
            entry_quality_category=category,
            has_blackbox=True,
        )

    def _load_real_cycles(self, profile: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id, c.timestamp, c.strategy_profile, c.symbol, c.direction,
                    c.status, c.open_price, c.close_price, c.quantity, c.stake_usdt,
                    c.net_profit, c.opened_at, c.closed_at, c.close_reason,
                    c.exchange_order_id, c.run_id,
                    COALESCE((
                        SELECT campaign_id
                        FROM real_pilot_campaigns
                        WHERE strategy_profile = c.strategy_profile
                          AND c.id > baseline_cycle_id
                          AND c.opened_at >= started_at
                          AND (finished_at IS NULL OR c.opened_at <= finished_at)
                        ORDER BY started_at DESC
                        LIMIT 1
                    ), (
                        SELECT campaign_id
                        FROM real_pilot_market_snapshots
                        WHERE real_cycle_id = c.id AND campaign_id IS NOT NULL
                        ORDER BY timestamp ASC, id ASC
                        LIMIT 1
                    ), c.run_id) AS campaign_id
                FROM real_pilot_cycles c
                WHERE c.strategy_profile = ?
                  AND c.status IN ('CLOSED', 'HALTED')
                ORDER BY c.id ASC
                """,
                (profile,),
            ).fetchall()
        keys = [
            "id", "timestamp", "strategy_profile", "symbol", "direction", "status",
            "open_price", "close_price", "quantity", "stake_usdt", "net_profit",
            "opened_at", "closed_at", "close_reason", "exchange_order_id", "run_id",
            "campaign_id",
        ]
        return [dict(zip(keys, row)) for row in rows]

    @staticmethod
    def _entry_snapshot(snapshots: list[dict[str, Any]], opened_at: datetime | None) -> dict[str, Any] | None:
        candidates = [row for row in snapshots if row.get("phase") == "entry"]
        if candidates:
            return candidates[0]
        candidates = [row for row in snapshots if row.get("phase") in {"tracking", "exit"}]
        if candidates:
            return candidates[0]
        if opened_at is None or not snapshots:
            return snapshots[0] if snapshots else None
        return min(snapshots, key=lambda row: abs(((_parse_time(row.get("timestamp")) or opened_at) - opened_at).total_seconds()))

    @staticmethod
    def _movement_after_entry(
        direction: str,
        entry_price: float | None,
        snapshots: list[dict[str, Any]],
        opened_at: datetime | None,
        offset_seconds: int,
    ) -> float | None:
        if entry_price is None or opened_at is None:
            return None
        target_time = opened_at + timedelta(seconds=offset_seconds)
        path = [row for row in snapshots if row.get("phase") in {"entry", "tracking", "exit", "post_exit"} and _float(row.get("price")) is not None]
        if not path:
            return None
        snapshot = min(path, key=lambda row: abs(((_parse_time(row.get("timestamp")) or target_time) - target_time).total_seconds()))
        price = _float(snapshot.get("price"))
        if price is None:
            return None
        if direction == "BUY_USDC":
            return price - entry_price
        return entry_price - price

    @staticmethod
    def _category(
        *,
        cycle: dict[str, Any],
        metrics,
        entry_spread: float | None,
        movements: dict[int, float | None],
        distance_from_center: float | None,
    ) -> str:
        if metrics.snapshots_count < 2 or metrics.max_favorable_excursion is None or metrics.max_adverse_excursion is None:
            return "insufficient_data"
        target_distance = abs(HFRealBlackboxDiagnosticsEngine.target_price(str(cycle["direction"]), float(cycle["open_price"])) - float(cycle["open_price"]))
        if metrics.target_touched and float(cycle.get("net_profit") or 0.0) > 0:
            return "good_entry_follow_through"
        first_move = next((movements[offset] for offset in (5, 15, 30, 60) if movements[offset] is not None), None)
        if first_move is not None and first_move < 0:
            return "immediate_adverse_move"
        movement_values = [abs(value) for value in movements.values() if value is not None]
        if entry_spread is not None and entry_spread > target_distance and metrics.max_favorable_excursion <= 0:
            return "spread_too_large"
        if movement_values and max(movement_values) <= target_distance * 0.2:
            return "no_movement_after_entry"
        if metrics.max_favorable_excursion < target_distance * 0.5 and metrics.max_adverse_excursion < 0:
            return "wrong_direction"
        if distance_from_center is not None and abs(distance_from_center) > target_distance * 3:
            return "late_entry"
        if not metrics.target_touched:
            return "weak_follow_through"
        return "insufficient_data"

    @staticmethod
    def _group_metrics(cycles: list[HFRealEntryCycleQuality]) -> HFRealEntryGroupMetrics:
        return HFRealEntryGroupMetrics(
            count=len(cycles),
            average_distance_from_center=_avg([abs(cycle.distance_from_short_center) for cycle in cycles if cycle.distance_from_short_center is not None]),
            average_entry_spread=_avg([cycle.entry_spread for cycle in cycles if cycle.entry_spread is not None]),
            average_mfe=_avg([cycle.max_favorable_excursion for cycle in cycles if cycle.max_favorable_excursion is not None]),
            average_mae=_avg([cycle.max_adverse_excursion for cycle in cycles if cycle.max_adverse_excursion is not None]),
            average_movement_5s=_avg([cycle.movement_after_5s for cycle in cycles if cycle.movement_after_5s is not None]),
            average_movement_15s=_avg([cycle.movement_after_15s for cycle in cycles if cycle.movement_after_15s is not None]),
            average_movement_30s=_avg([cycle.movement_after_30s for cycle in cycles if cycle.movement_after_30s is not None]),
            average_movement_60s=_avg([cycle.movement_after_60s for cycle in cycles if cycle.movement_after_60s is not None]),
            target_touch_rate=(sum(1 for cycle in cycles if cycle.target_touched) / len(cycles)) if cycles else 0.0,
            timeout_loss_rate=(sum(1 for cycle in cycles if HFRealEntryQualityDiagnosticsEngine._is_timeout_reason(cycle.close_reason) and cycle.net_profit < 0) / len(cycles)) if cycles else 0.0,
            buy_count=sum(1 for cycle in cycles if cycle.direction == "BUY_USDC"),
            sell_count=sum(1 for cycle in cycles if cycle.direction == "SELL_USDC"),
        )

    @staticmethod
    def _main_issue(
        cycles: list[HFRealEntryCycleQuality],
        timeout_no_touch_count: int,
        timeout_loss_count: int,
        cycles_without_blackbox: int,
    ) -> str:
        if not cycles:
            return "insufficient_data" if cycles_without_blackbox else "no_real_cycles"
        category_counts: dict[str, int] = {}
        for cycle in cycles:
            category_counts[cycle.entry_quality_category] = category_counts.get(cycle.entry_quality_category, 0) + 1
        dominant = max(category_counts.items(), key=lambda item: item[1])[0]
        if timeout_no_touch_count >= max(1, len(cycles) // 2):
            return "target_not_touched"
        if timeout_loss_count >= max(1, len(cycles) // 2):
            return "timeout_losses"
        return dominant

    @staticmethod
    def _recommendation(cycles: list[HFRealEntryCycleQuality], main_issue: str, cycles_without_blackbox: int) -> str:
        if not cycles:
            return "RUN_MORE_BLACKBOX_SMALL_REAL" if cycles_without_blackbox else "RUN_MORE_BLACKBOX_SMALL_REAL"
        if len(cycles) < 10:
            return "RUN_MORE_BLACKBOX_SMALL_REAL"
        if main_issue in {"immediate_adverse_move", "wrong_direction", "weak_follow_through"}:
            return "TUNE_ENTRY_CONFIRMATION"
        if main_issue in {"target_not_touched", "timeout_losses"}:
            return "TUNE_TIMEOUT_POLICY"
        if main_issue == "spread_too_large":
            return "KEEP_REAL_PAUSED"
        if main_issue == "no_movement_after_entry":
            return "TUNE_TARGET_DISTANCE"
        return "READY_FOR_NEXT_CAMPAIGN"

    @staticmethod
    def _campaign_id(cycle: dict[str, Any]) -> str:
        return str(cycle.get("campaign_id") or cycle.get("run_id") or "N/A")

    @staticmethod
    def _is_timeout_reason(reason: str | None) -> bool:
        text = str(reason or "")
        return "holding" in text or "timeout" in text


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _positive_bool(value: float | None) -> bool | None:
    if value is None:
        return None
    return value > 0


def _avg(values: list[float]) -> float | None:
    return mean(values) if values else None
