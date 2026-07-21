from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFRealBlackboxMetrics:
    snapshots_count: int
    pre_entry_count: int
    tracking_count: int
    exit_count: int
    post_exit_count: int
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    target_touched: bool
    reference_target_touched: bool
    executable_target_touched: bool
    real_target_close_triggered: bool
    first_target_touch_seconds: float | None
    first_executable_target_touch_seconds: float | None
    nearest_target_distance: float | None
    nearest_target_seconds: float | None
    max_favorable_price: float | None
    max_adverse_price: float | None
    min_price: float | None
    max_price: float | None
    average_spread: float | None
    max_spread: float | None
    entry_market_price: float | None
    exit_market_price: float | None
    entry_execution_gap: float | None
    close_execution_gap: float | None
    suspected_reason: str


@dataclass(frozen=True)
class HFRealBlackboxReport:
    profile: str
    real_cycle_id: int
    cycle: dict[str, Any] | None
    snapshots: list[dict[str, Any]]
    metrics: HFRealBlackboxMetrics | None
    recommendation: str


class HFRealBlackboxRecorder:
    PRE_ENTRY_ATTACH_SECONDS = 60

    def __init__(self, database: DatabaseManager, symbol: str) -> None:
        self.database = database
        self.symbol = symbol

    def record_signal_snapshot(
        self,
        *,
        phase: str,
        signal,
        campaign_id: str | None = None,
        real_cycle_id: int | None = None,
        direction: str | None = None,
        target_price: float | None = None,
        distance_to_target: float | None = None,
        unrealized_pnl: float | None = None,
        open_real_cycles: int | None = None,
        raw_payload_json: str | None = None,
    ) -> int:
        price = _float(getattr(signal, "price", None))
        bid = _float(getattr(signal, "bid", None))
        ask = _float(getattr(signal, "ask", None))
        spread = _float(getattr(signal, "spread", None))
        mid = _float(getattr(signal, "mid", None))
        if mid is None and bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        if spread is None and bid is not None and ask is not None:
            spread = ask - bid
        return self.database.save_real_pilot_market_snapshot(
            real_cycle_id=real_cycle_id,
            campaign_id=campaign_id,
            phase=phase,
            symbol=self.symbol,
            price=price,
            bid=bid,
            ask=ask,
            mid=mid,
            spread=spread,
            short_center=_float(getattr(signal, "short_center", None)),
            hf_entry_mode=getattr(signal, "hf_entry_mode", None),
            candidate=getattr(signal, "candidate", None),
            block_reason=getattr(signal, "block_reason", None),
            direction=direction or getattr(signal, "entry_signal", None),
            target_price=target_price,
            distance_to_target=distance_to_target,
            unrealized_pnl=unrealized_pnl,
            open_real_cycles=open_real_cycles,
            source=getattr(signal, "source", None) or "real_pilot_signal",
            raw_payload_json=raw_payload_json or getattr(signal, "raw_payload_json", None),
        )

    def record_close_snapshot(
        self,
        *,
        phase: str,
        update,
        real_cycle_id: int,
        campaign_id: str | None = None,
        direction: str | None = None,
        open_real_cycles: int | None = None,
        raw_payload_json: str | None = None,
    ) -> int:
        bid = _float(getattr(update, "bid", None))
        ask = _float(getattr(update, "ask", None))
        spread = _float(getattr(update, "spread", None))
        mid = _float(getattr(update, "mid", None))
        if mid is None and bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        price = _float(getattr(update, "current_price", None))
        if price is None:
            price = mid
        return self.database.save_real_pilot_market_snapshot(
            real_cycle_id=real_cycle_id,
            campaign_id=campaign_id,
            phase=phase,
            symbol=self.symbol,
            price=price,
            bid=bid,
            ask=ask,
            mid=mid,
            spread=spread,
            short_center=None,
            hf_entry_mode=None,
            candidate=None,
            block_reason=None,
            direction=direction,
            target_price=_float(getattr(update, "target_price", None)),
            distance_to_target=_float(getattr(update, "distance_to_target", None)),
            unrealized_pnl=_float(getattr(update, "unrealized_pnl", None)),
            open_real_cycles=open_real_cycles,
            source="real_pilot_close_watch",
            raw_payload_json=raw_payload_json,
        )

    def attach_recent_pre_entry(self, *, real_cycle_id: int, campaign_id: str | None) -> int:
        since = datetime.now(timezone.utc).timestamp() - self.PRE_ENTRY_ATTACH_SECONDS
        since_timestamp = datetime.fromtimestamp(since, timezone.utc).replace(tzinfo=None).isoformat()
        return self.database.attach_recent_real_pilot_market_snapshots(
            real_cycle_id=real_cycle_id,
            campaign_id=campaign_id,
            since_timestamp=since_timestamp,
        )


class HFRealBlackboxDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, *, profile: str, real_cycle_id: int) -> HFRealBlackboxReport:
        cycle = self.database.load_real_pilot_cycle_by_id(real_cycle_id, profile)
        if cycle is None:
            return HFRealBlackboxReport(
                profile=profile,
                real_cycle_id=real_cycle_id,
                cycle=None,
                snapshots=[],
                metrics=None,
                recommendation="CYCLE_NOT_FOUND",
            )
        snapshots = self.database.load_real_pilot_market_snapshots(real_cycle_id)
        if not snapshots:
            return HFRealBlackboxReport(
                profile=profile,
                real_cycle_id=real_cycle_id,
                cycle=cycle,
                snapshots=[],
                metrics=None,
                recommendation="RUN_NEW_CAMPAIGN_WITH_RECORDER",
            )
        metrics = self.calculate_metrics(cycle, snapshots)
        return HFRealBlackboxReport(
            profile=profile,
            real_cycle_id=real_cycle_id,
            cycle=cycle,
            snapshots=snapshots,
            metrics=metrics,
            recommendation=self._recommendation(metrics),
        )

    @classmethod
    def calculate_metrics(cls, cycle: dict[str, Any], snapshots: list[dict[str, Any]]) -> HFRealBlackboxMetrics:
        direction = str(cycle["direction"])
        open_price = float(cycle["open_price"])
        close_price = _float(cycle.get("close_price"))
        target_price = cls.target_price(direction, open_price)
        opened_at = _parse_time(cycle.get("opened_at"))
        path_snapshots = [row for row in snapshots if row.get("phase") in {"entry", "tracking", "exit", "post_exit"}]
        prices = [_float(row.get("price")) for row in path_snapshots]
        prices = [price for price in prices if price is not None]
        spreads = [_float(row.get("spread")) for row in snapshots]
        spreads = [spread for spread in spreads if spread is not None]
        phase_counts = {phase: sum(1 for row in snapshots if row.get("phase") == phase) for phase in ("pre_entry", "tracking", "exit", "post_exit")}
        reference_target_rows = [
            row for row in path_snapshots
            if _float(row.get("price")) is not None and cls.target_hit(direction, float(row["price"]), target_price)
        ]
        executable_target_rows = [
            row for row in path_snapshots
            if cls._executable_close_reference(direction, row) is not None
            and cls.target_hit(direction, cls._executable_close_reference(direction, row), target_price)
        ]
        nearest_row = None
        if prices:
            nearest_row = min(
                path_snapshots,
                key=lambda row: abs((_float(row.get("price")) or target_price) - target_price),
            )
        nearest_distance = abs((_float(nearest_row.get("price")) or target_price) - target_price) if nearest_row else None
        nearest_seconds = cls._seconds_from_open(opened_at, nearest_row) if nearest_row else None
        first_touch_seconds = cls._seconds_from_open(opened_at, reference_target_rows[0]) if reference_target_rows else None
        first_executable_touch_seconds = (
            cls._seconds_from_open(opened_at, executable_target_rows[0]) if executable_target_rows else None
        )
        max_favorable_price = cls._best_price(direction, prices)
        max_adverse_price = cls._worst_price(direction, prices)
        mfe = cls._pnl_per_unit(direction, open_price, max_favorable_price) if max_favorable_price is not None else None
        mae = cls._pnl_per_unit(direction, open_price, max_adverse_price) if max_adverse_price is not None else None
        entry_market_price = _float(next((row.get("price") for row in snapshots if row.get("phase") in {"entry", "pre_entry"}), None))
        exit_market_price = _float(next((row.get("price") for row in reversed(snapshots) if row.get("phase") == "exit"), None))
        if exit_market_price is None:
            exit_market_price = _float((path_snapshots[-1] if path_snapshots else snapshots[-1]).get("price"))
        suspected_reason = cls._suspected_reason(
            reference_target_touched=bool(reference_target_rows),
            executable_target_touched=bool(executable_target_rows),
            real_target_close_triggered=str(cycle.get("close_reason") or "") == "real_pilot_target",
            close_reason=str(cycle.get("close_reason") or ""),
            close_price=close_price,
            exit_market_price=exit_market_price,
            nearest_distance=nearest_distance,
            snapshots=snapshots,
        )
        return HFRealBlackboxMetrics(
            snapshots_count=len(snapshots),
            pre_entry_count=phase_counts["pre_entry"],
            tracking_count=phase_counts["tracking"],
            exit_count=phase_counts["exit"],
            post_exit_count=phase_counts["post_exit"],
            max_favorable_excursion=mfe,
            max_adverse_excursion=mae,
            target_touched=bool(reference_target_rows),
            reference_target_touched=bool(reference_target_rows),
            executable_target_touched=bool(executable_target_rows),
            real_target_close_triggered=str(cycle.get("close_reason") or "") == "real_pilot_target",
            first_target_touch_seconds=first_touch_seconds,
            first_executable_target_touch_seconds=first_executable_touch_seconds,
            nearest_target_distance=nearest_distance,
            nearest_target_seconds=nearest_seconds,
            max_favorable_price=max_favorable_price,
            max_adverse_price=max_adverse_price,
            min_price=min(prices) if prices else None,
            max_price=max(prices) if prices else None,
            average_spread=mean(spreads) if spreads else None,
            max_spread=max(spreads) if spreads else None,
            entry_market_price=entry_market_price,
            exit_market_price=exit_market_price,
            entry_execution_gap=(open_price - entry_market_price) if entry_market_price is not None else None,
            close_execution_gap=(close_price - exit_market_price) if close_price is not None and exit_market_price is not None else None,
            suspected_reason=suspected_reason,
        )

    @staticmethod
    def target_price(direction: str, open_price: float) -> float:
        if direction == "BUY_USDC":
            return open_price * (1.0 + HF_MICRO_TARGET_PROFIT)
        return open_price * (1.0 - HF_MICRO_TARGET_PROFIT)

    @staticmethod
    def target_hit(direction: str, price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return price >= target_price
        return price <= target_price

    @staticmethod
    def executable_target_hit(direction: str, snapshot: dict[str, Any], target_price: float) -> bool | None:
        reference = HFRealBlackboxDiagnosticsEngine._executable_close_reference(direction, snapshot)
        if reference is None:
            return None
        return HFRealBlackboxDiagnosticsEngine.target_hit(direction, reference, target_price)

    @staticmethod
    def _executable_close_reference(direction: str, snapshot: dict[str, Any]) -> float | None:
        if direction == "BUY_USDC":
            return _float(snapshot.get("bid"))
        return _float(snapshot.get("ask"))

    @staticmethod
    def _pnl_per_unit(direction: str, open_price: float, price: float | None) -> float | None:
        if price is None:
            return None
        if direction == "BUY_USDC":
            return price - open_price
        return open_price - price

    @classmethod
    def _best_price(cls, direction: str, prices: list[float]) -> float | None:
        if not prices:
            return None
        return max(prices) if direction == "BUY_USDC" else min(prices)

    @classmethod
    def _worst_price(cls, direction: str, prices: list[float]) -> float | None:
        if not prices:
            return None
        return min(prices) if direction == "BUY_USDC" else max(prices)

    @staticmethod
    def _seconds_from_open(opened_at: datetime | None, row: dict[str, Any] | None) -> float | None:
        if opened_at is None or row is None:
            return None
        timestamp = _parse_time(row.get("timestamp"))
        if timestamp is None:
            return None
        return max(0.0, (timestamp - opened_at).total_seconds())

    @staticmethod
    def _suspected_reason(
        *,
        reference_target_touched: bool,
        executable_target_touched: bool,
        real_target_close_triggered: bool,
        close_reason: str,
        close_price: float | None,
        exit_market_price: float | None,
        nearest_distance: float | None,
        snapshots: list[dict[str, Any]],
    ) -> str:
        if not snapshots:
            return "data_insufficient"
        if executable_target_touched and not real_target_close_triggered:
            return "target_touched_but_not_executed"
        if reference_target_touched and not executable_target_touched and "target" not in close_reason:
            return "reference_touch_only"
        if (not reference_target_touched) and ("holding" in close_reason or "timeout" in close_reason):
            return "target_not_touched"
        if nearest_distance is not None and nearest_distance <= 0.000005 and ("holding" in close_reason or "timeout" in close_reason):
            return "timeout_before_recovery"
        if close_price is not None and exit_market_price is not None and abs(close_price - exit_market_price) > 0.00001:
            return "spread_prevented_close"
        return "unknown"

    @staticmethod
    def _recommendation(metrics: HFRealBlackboxMetrics) -> str:
        if metrics.snapshots_count < 3:
            return "COLLECT_MORE_BLACKBOX_DATA"
        if metrics.suspected_reason in {"target_touched_but_not_executed", "spread_prevented_close"}:
            return "COMPARE_EXECUTION_AND_SPREAD"
        if metrics.suspected_reason in {"target_not_touched", "timeout_before_recovery"}:
            return "REVIEW_TIMEOUT_POLICY"
        return "BLACKBOX_DATA_AVAILABLE"


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
