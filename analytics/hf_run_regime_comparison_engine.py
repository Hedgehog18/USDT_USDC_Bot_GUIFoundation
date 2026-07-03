from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median

from analytics.hf_extreme_price import is_extreme_close_price
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFRunDirectionBreakdown:
    count: int
    win_rate: float
    net_profit: float
    timeout_loss_count: int


@dataclass(frozen=True)
class HFRunEntryContextSummary:
    available_count: int
    missing_count: int
    hf_entry_mode_distribution: dict[str, int]
    previous_price_relation_distribution: dict[str, int]
    last_different_price_relation_distribution: dict[str, int]
    flat_price_buffer_count: int
    equal_center_fallback_count: int
    average_short_center_distance: float | None
    average_price_buffer_unique_values: float | None
    average_flat_samples_count: float | None
    average_price_velocity: float | None
    average_short_term_drift: float | None
    direction_confirmed_count: int
    direction_not_confirmed_count: int


@dataclass(frozen=True)
class HFRunLossDiagnostics:
    losing_cycles_count: int
    categories: dict[str, int]
    no_follow_through_count: int
    average_adverse_move: float | None
    average_favorable_move: float | None
    target_touched_count: int
    near_target_count: int
    near_target_samples: str


@dataclass(frozen=True)
class HFRunRegimeSeriesSummary:
    label: str
    since_id: int
    limit: int | None
    cycles_count: int
    net_profit: float
    net_profit_without_extreme: float
    extreme_cycles_count: int
    win_rate: float
    win_rate_without_extreme: float
    target_closed_count: int
    timeout_closed_count: int
    breakeven_count: int
    average_net: float
    median_net: float
    run_duration_seconds: float | None
    cycles_per_hour: float
    cycles_per_day_estimate: float
    average_holding_seconds: float | None
    median_holding_seconds: float | None
    buy: HFRunDirectionBreakdown
    sell: HFRunDirectionBreakdown
    entry_context: HFRunEntryContextSummary
    loss_diagnostics: HFRunLossDiagnostics


@dataclass(frozen=True)
class HFRunRegimeComparisonReport:
    profile: str
    run_a: HFRunRegimeSeriesSummary
    run_b: HFRunRegimeSeriesSummary
    differences: list[str]
    recommendation: str


class HFRunRegimeComparisonEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def compare(
        self,
        *,
        profile: str,
        run_a_since_id: int,
        run_b_since_id: int,
        limit: int | None = None,
    ) -> HFRunRegimeComparisonReport:
        run_a_until_id = run_b_since_id if run_b_since_id > run_a_since_id else None
        run_b_until_id = run_a_since_id if run_a_since_id > run_b_since_id else None
        run_a = self._summary("Run A", profile, run_a_since_id, limit, until_id=run_a_until_id)
        run_b = self._summary("Run B", profile, run_b_since_id, limit, until_id=run_b_until_id)
        differences = self._differences(run_a, run_b)
        return HFRunRegimeComparisonReport(
            profile=profile,
            run_a=run_a,
            run_b=run_b,
            differences=differences,
            recommendation=self._recommendation(run_a, run_b),
        )

    def _summary(
        self,
        label: str,
        profile: str,
        since_id: int,
        limit: int | None,
        until_id: int | None = None,
    ) -> HFRunRegimeSeriesSummary:
        rows = self._load_rows(profile, since_id, limit, until_id=until_id)
        non_extreme_rows = [
            row for row in rows
            if not is_extreme_close_price(self._float(row["close_price"]))
        ]
        net_values = [self._float(row["net_profit"]) for row in rows]
        holding_values = [value for value in (self._holding_seconds(row) for row in rows) if value is not None]
        closed_count = len(rows)
        win_count = sum(1 for value in net_values if value > 0)
        non_extreme_win_count = sum(1 for row in non_extreme_rows if self._float(row["net_profit"]) > 0)
        target_count = sum(1 for row in rows if self._close_reason(row) == "target")
        timeout_count = sum(1 for row in rows if self._is_timeout(row))
        breakeven_count = sum(1 for value in net_values if value == 0)
        duration = self._run_duration_seconds(rows)
        return HFRunRegimeSeriesSummary(
            label=label,
            since_id=since_id,
            limit=limit,
            cycles_count=closed_count,
            net_profit=sum(net_values),
            net_profit_without_extreme=sum(self._float(row["net_profit"]) for row in non_extreme_rows),
            extreme_cycles_count=closed_count - len(non_extreme_rows),
            win_rate=(win_count / closed_count) if closed_count else 0.0,
            win_rate_without_extreme=(
                non_extreme_win_count / len(non_extreme_rows)
                if non_extreme_rows else 0.0
            ),
            target_closed_count=target_count,
            timeout_closed_count=timeout_count,
            breakeven_count=breakeven_count,
            average_net=mean(net_values) if net_values else 0.0,
            median_net=median(net_values) if net_values else 0.0,
            run_duration_seconds=duration,
            cycles_per_hour=(closed_count / (duration / 3600.0)) if duration and duration > 0 else 0.0,
            cycles_per_day_estimate=(closed_count / (duration / 86400.0)) if duration and duration > 0 else 0.0,
            average_holding_seconds=mean(holding_values) if holding_values else None,
            median_holding_seconds=median(holding_values) if holding_values else None,
            buy=self._direction_breakdown(rows, "BUY_USDC"),
            sell=self._direction_breakdown(rows, "SELL_USDC"),
            entry_context=self._entry_context(rows),
            loss_diagnostics=self._loss_diagnostics(rows),
        )

    def _load_rows(
        self,
        profile: str,
        since_id: int,
        limit: int | None,
        *,
        until_id: int | None = None,
    ) -> list[dict]:
        limit_clause = "" if limit is None else "LIMIT ?"
        params: list[object] = [profile, since_id]
        until_clause = ""
        if until_id is not None:
            until_clause = "AND pc.id <= ?"
            params.append(until_id)
        if limit is not None:
            params.append(int(limit))
        with self.database.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    pc.id, pc.timestamp, pc.direction, pc.status, pc.open_price,
                    pc.close_price, pc.quantity, pc.net_profit, pc.opened_at,
                    pc.closed_at, pc.close_reason, pc.max_favorable_pnl,
                    pc.max_adverse_pnl, pc.was_target_touched, pc.was_near_target,
                    diag.current_price, diag.short_center, diag.previous_price,
                    diag.last_different_price, diag.hf_entry_mode,
                    diag.price_buffer_unique_values, diag.flat_samples_count,
                    diag.flat_price_buffer, diag.entry_direction, diag.entry_reason
                FROM paper_cycles pc
                LEFT JOIN hf_paper_cycle_entry_diagnostics diag
                    ON diag.paper_cycle_id = pc.id
                WHERE pc.strategy_profile = ?
                  AND pc.id > ?
                  {until_clause}
                  AND pc.status IN ('CLOSED', 'CLOSED_MANUAL')
                ORDER BY pc.id ASC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        keys = (
            "id", "timestamp", "direction", "status", "open_price", "close_price",
            "quantity", "net_profit", "opened_at", "closed_at", "close_reason",
            "max_favorable_pnl", "max_adverse_pnl", "was_target_touched", "was_near_target",
            "entry_current_price", "short_center", "previous_price", "last_different_price",
            "hf_entry_mode", "price_buffer_unique_values", "flat_samples_count",
            "flat_price_buffer", "entry_direction", "entry_reason",
        )
        return [dict(zip(keys, row)) for row in rows]

    def _direction_breakdown(self, rows: list[dict], direction: str) -> HFRunDirectionBreakdown:
        direction_rows = [row for row in rows if str(row["direction"]) == direction]
        count = len(direction_rows)
        wins = sum(1 for row in direction_rows if self._float(row["net_profit"]) > 0)
        return HFRunDirectionBreakdown(
            count=count,
            win_rate=(wins / count) if count else 0.0,
            net_profit=sum(self._float(row["net_profit"]) for row in direction_rows),
            timeout_loss_count=sum(
                1 for row in direction_rows
                if self._is_timeout(row) and self._float(row["net_profit"]) < 0
            ),
        )

    def _entry_context(self, rows: list[dict]) -> HFRunEntryContextSummary:
        context_rows = [row for row in rows if row["hf_entry_mode"] is not None]
        missing_count = len(rows) - len(context_rows)
        mode_counts = Counter(str(row["hf_entry_mode"] or "N/A") for row in context_rows)
        previous_relations = Counter(self._relation(row["entry_current_price"], row["previous_price"]) for row in context_rows)
        last_diff_relations = Counter(self._relation(row["entry_current_price"], row["last_different_price"]) for row in context_rows)
        short_distances = [
            self._float(row["entry_current_price"]) - self._float(row["short_center"])
            for row in context_rows
            if row["entry_current_price"] is not None and row["short_center"] is not None
        ]
        unique_values = [
            int(row["price_buffer_unique_values"])
            for row in context_rows
            if row["price_buffer_unique_values"] is not None
        ]
        flat_samples = [
            int(row["flat_samples_count"])
            for row in context_rows
            if row["flat_samples_count"] is not None
        ]
        velocities = [
            self._float(row["entry_current_price"]) - self._float(row["previous_price"])
            for row in context_rows
            if row["entry_current_price"] is not None and row["previous_price"] is not None
        ]
        drifts = [
            self._float(row["entry_current_price"]) - self._float(row["last_different_price"])
            for row in context_rows
            if row["entry_current_price"] is not None and row["last_different_price"] is not None
        ]
        confirmed = sum(1 for row in context_rows if self._direction_confirmed(row))
        return HFRunEntryContextSummary(
            available_count=len(context_rows),
            missing_count=missing_count,
            hf_entry_mode_distribution=dict(mode_counts),
            previous_price_relation_distribution=dict(previous_relations),
            last_different_price_relation_distribution=dict(last_diff_relations),
            flat_price_buffer_count=sum(1 for row in context_rows if int(row["flat_price_buffer"] or 0) == 1),
            equal_center_fallback_count=sum(
                1 for row in context_rows
                if "equal_center_last_different_fallback" in str(row["hf_entry_mode"] or row["entry_reason"] or "")
            ),
            average_short_center_distance=mean(short_distances) if short_distances else None,
            average_price_buffer_unique_values=mean(unique_values) if unique_values else None,
            average_flat_samples_count=mean(flat_samples) if flat_samples else None,
            average_price_velocity=mean(velocities) if velocities else None,
            average_short_term_drift=mean(drifts) if drifts else None,
            direction_confirmed_count=confirmed,
            direction_not_confirmed_count=len(context_rows) - confirmed,
        )

    def _loss_diagnostics(self, rows: list[dict]) -> HFRunLossDiagnostics:
        losing_rows = [row for row in rows if self._float(row["net_profit"]) < 0]
        categories = Counter(self._loss_category(row) for row in losing_rows)
        adverse = [self._float(row["max_adverse_pnl"]) for row in losing_rows if row["max_adverse_pnl"] is not None]
        favorable = [self._float(row["max_favorable_pnl"]) for row in losing_rows if row["max_favorable_pnl"] is not None]
        return HFRunLossDiagnostics(
            losing_cycles_count=len(losing_rows),
            categories=dict(categories),
            no_follow_through_count=categories.get("no_follow_through", 0),
            average_adverse_move=mean(adverse) if adverse else None,
            average_favorable_move=mean(favorable) if favorable else None,
            target_touched_count=sum(1 for row in losing_rows if int(row["was_target_touched"] or 0) == 1),
            near_target_count=sum(1 for row in losing_rows if int(row["was_near_target"] or 0) == 1),
            near_target_samples="N/A",
        )

    def _loss_category(self, row: dict) -> str:
        if int(row["flat_price_buffer"] or 0) == 1:
            return "flat_market_entry"
        if int(row["was_near_target"] or 0) == 1:
            return "target_missed_by_one_tick"
        if self._float(row["max_favorable_pnl"]) <= 0:
            return "no_follow_through"
        if abs(self._float(row["max_adverse_pnl"])) > abs(self._float(row["max_favorable_pnl"])):
            return "adverse_spike"
        return "unknown_insufficient_data"

    def _differences(
        self,
        run_a: HFRunRegimeSeriesSummary,
        run_b: HFRunRegimeSeriesSummary,
    ) -> list[str]:
        differences: list[str] = []
        if run_b.win_rate_without_extreme + 0.05 < run_a.win_rate_without_extreme:
            differences.append("Run B has lower win rate without extreme cycles.")
        if run_b.cycles_per_hour + 1.0 < run_a.cycles_per_hour:
            differences.append("Run B has lower cycles/hour.")
        if self._greater(run_b.entry_context.average_flat_samples_count, run_a.entry_context.average_flat_samples_count, 2.0):
            differences.append("Run B has higher flat_samples_count.")
        if self._lower(run_b.entry_context.average_price_buffer_unique_values, run_a.entry_context.average_price_buffer_unique_values, 1.0):
            differences.append("Run B has lower price_buffer_unique_values.")
        if run_b.loss_diagnostics.no_follow_through_count > run_a.loss_diagnostics.no_follow_through_count:
            differences.append("Run B has more no_follow_through losses.")
        if run_b.buy.timeout_loss_count > run_a.buy.timeout_loss_count:
            differences.append("Run B has more BUY timeout losses.")
        if run_b.sell.timeout_loss_count > run_a.sell.timeout_loss_count:
            differences.append("Run B has more SELL timeout losses.")
        if not differences:
            differences.append("No strong regime difference detected with available diagnostics.")
        return differences

    def _recommendation(
        self,
        run_a: HFRunRegimeSeriesSummary,
        run_b: HFRunRegimeSeriesSummary,
    ) -> str:
        if run_a.cycles_count < 20 or run_b.cycles_count < 20:
            return "NEED_MORE_DATA"
        if self._greater(run_b.entry_context.average_flat_samples_count, run_a.entry_context.average_flat_samples_count, 2.0):
            return "ADD_MARKET_REGIME_FILTER"
        if run_b.loss_diagnostics.no_follow_through_count > run_a.loss_diagnostics.no_follow_through_count:
            return "ADD_ENTRY_CONFIRMATION"
        if abs(run_b.entry_context.average_price_velocity or 0.0) > abs(run_a.entry_context.average_price_velocity or 0.0):
            return "ADD_PRICE_VELOCITY_FILTER"
        return "KEEP_BASELINE"

    def _relation(self, left: object, right: object) -> str:
        if left is None or right is None:
            return "N/A"
        left_value = self._float(left)
        right_value = self._float(right)
        if left_value > right_value:
            return "above"
        if left_value < right_value:
            return "below"
        return "equal"

    def _direction_confirmed(self, row: dict) -> bool:
        if row["entry_current_price"] is None or row["previous_price"] is None:
            return False
        velocity = self._float(row["entry_current_price"]) - self._float(row["previous_price"])
        direction = str(row["direction"])
        return (direction == "BUY_USDC" and velocity > 0) or (direction == "SELL_USDC" and velocity < 0)

    def _run_duration_seconds(self, rows: list[dict]) -> float | None:
        times = []
        for row in rows:
            for key in ("opened_at", "closed_at"):
                value = self._parse_datetime(row.get(key))
                if value is not None:
                    times.append(value)
        if len(times) < 2:
            return None
        return max(0.0, (max(times) - min(times)).total_seconds())

    def _holding_seconds(self, row: dict) -> float | None:
        opened = self._parse_datetime(row.get("opened_at"))
        closed = self._parse_datetime(row.get("closed_at"))
        if opened is None or closed is None:
            return None
        return max(0.0, (closed - opened).total_seconds())

    def _parse_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _is_timeout(self, row: dict) -> bool:
        reason = self._close_reason(row)
        return reason.startswith("max_holding_") or "timeout" in reason

    def _close_reason(self, row: dict) -> str:
        return str(row.get("close_reason") or "")

    def _float(self, value: object) -> float:
        return float(value or 0.0)

    def _greater(self, left: float | None, right: float | None, threshold: float) -> bool:
        if left is None or right is None:
            return False
        return left > right + threshold

    def _lower(self, left: float | None, right: float | None, threshold: float) -> bool:
        if left is None or right is None:
            return False
        return left + threshold < right
