from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from math import floor
from pathlib import Path
from typing import Any, Callable, Protocol

from config.config_manager import BotConfig
from market.binance_market_data_provider import BinanceMarketDataProvider, BidAsk
from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT
from storage.database_manager import DatabaseManager


POST_EXIT_OBSERVER_COMPLETED = "COMPLETED"
POST_EXIT_OBSERVER_FAILED = "FAILED"
POST_EXIT_OBSERVER_DISABLED = "DISABLED"
POST_EXIT_OBSERVER_CYCLE_NOT_FOUND = "CYCLE_NOT_FOUND"
POST_EXIT_OBSERVER_CYCLE_NOT_CLOSED = "CYCLE_NOT_CLOSED"
PRICE_QUANTUM = Decimal("0.00000001")


class PostExitMarketProvider(Protocol):
    def get_bid_ask(self, symbol: str) -> BidAsk:
        ...


@dataclass(frozen=True)
class PostExitObserverResult:
    real_cycle_id: int
    status: str
    snapshots_count: int
    post_exit_mfe: float | None
    post_exit_mae: float | None
    max_price: float | None
    min_price: float | None
    post_exit_target_touched: bool | None
    time_to_post_target: float | None
    closest_distance_after_exit: float | None
    target_was_reached_before_exit: bool | None = None
    target_satisfied_at_observer_start: bool | None = None
    target_revisited_after_exit: bool | None = None
    time_to_target_revisit: float | None = None
    expected_snapshots_count: int | None = None
    effective_average_interval_seconds: float | None = None
    error: str | None = None


class HFPostExitObserver:
    def __init__(
        self,
        database: DatabaseManager,
        config: BotConfig,
        market_provider: PostExitMarketProvider | None = None,
    ) -> None:
        self.database = database
        self.config = config
        self.market_provider = market_provider or BinanceMarketDataProvider(base_url=config.binance_base_url)

    def observe(
        self,
        *,
        profile: str,
        real_cycle_id: int,
        duration_seconds: float | None = None,
        interval_seconds: float | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        now_fn: Callable[[], datetime] = datetime.utcnow,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> PostExitObserverResult:
        duration = float(duration_seconds if duration_seconds is not None else self.config.post_exit_observer_duration_seconds)
        interval = float(interval_seconds if interval_seconds is not None else self.config.post_exit_observer_interval_seconds)
        if not self.config.post_exit_observer_enabled:
            return self._store_terminal_summary(
                real_cycle_id=real_cycle_id,
                campaign_id=None,
                started_at=now_fn().isoformat(),
                duration_seconds=duration,
                interval_seconds=interval,
                status=POST_EXIT_OBSERVER_DISABLED,
                error=None,
            )
        if duration < 0:
            raise ValueError("duration_seconds must be 0 or greater.")
        if interval <= 0:
            raise ValueError("interval_seconds must be greater than 0.")

        cycle = self.database.load_real_pilot_cycle_by_id(real_cycle_id, profile)
        if cycle is None:
            return self._store_terminal_summary(
                real_cycle_id=real_cycle_id,
                campaign_id=None,
                started_at=now_fn().isoformat(),
                duration_seconds=duration,
                interval_seconds=interval,
                status=POST_EXIT_OBSERVER_CYCLE_NOT_FOUND,
                error="real pilot cycle not found",
            )
        if cycle["status"] != "CLOSED" or not cycle.get("closed_at"):
            return self._store_terminal_summary(
                real_cycle_id=real_cycle_id,
                campaign_id=self._campaign_id(real_cycle_id),
                started_at=now_fn().isoformat(),
                duration_seconds=duration,
                interval_seconds=interval,
                status=POST_EXIT_OBSERVER_CYCLE_NOT_CLOSED,
                error=f"cycle status={cycle['status']}",
            )

        started_at = now_fn()
        finished_at = started_at + timedelta(seconds=duration)
        start_monotonic = monotonic_fn()
        target_price = self.target_price(cycle["direction"], cycle["open_price"])
        campaign_id = self._campaign_id(real_cycle_id)
        center = self._latest_short_center(real_cycle_id)
        sample_number = 0
        error: str | None = None
        while True:
            scheduled_sample_at = start_monotonic + sample_number * interval
            if scheduled_sample_at - start_monotonic > duration:
                break
            current_monotonic = monotonic_fn()
            if current_monotonic < scheduled_sample_at:
                sleep_fn(scheduled_sample_at - current_monotonic)
            try:
                now = now_fn()
                seconds_after_exit = max(0.0, (now - _parse_time(cycle["closed_at"], fallback=started_at)).total_seconds())
                bid_ask = self.market_provider.get_bid_ask(cycle["symbol"])
                price = _decimal(bid_ask.mid_price)
                bid = _decimal(bid_ask.bid)
                ask = _decimal(bid_ask.ask)
                mid = _decimal(bid_ask.mid_price)
                spread = _decimal(bid_ask.spread)
                entry_price = _decimal(cycle["open_price"])
                center_decimal = _decimal(center)
                self.database.save_real_pilot_post_exit_snapshot(
                    real_cycle_id=real_cycle_id,
                    campaign_id=campaign_id,
                    timestamp=now.isoformat(),
                    seconds_after_exit=seconds_after_exit,
                    symbol=cycle["symbol"],
                    price=float(price),
                    bid=float(bid),
                    ask=float(ask),
                    mid=float(mid),
                    spread=float(spread),
                    entry_price=float(entry_price),
                    target_price=float(target_price),
                    distance_from_entry=float(self._directional_move(cycle["direction"], entry_price, price)),
                    distance_to_target=float(self._distance_to_target(cycle["direction"], price, target_price)),
                    distance_to_center=float(price - center_decimal) if center_decimal is not None else None,
                    source="post_exit_observer",
                    raw_payload_json=None,
                )
            except Exception as exc:  # research recorder should report failures explicitly.
                error = str(exc)
                break
            elapsed_after_sample = monotonic_fn() - start_monotonic
            sample_number = max(sample_number + 1, int(floor(elapsed_after_sample / interval)) + 1)

        snapshots = self.database.load_real_pilot_post_exit_snapshots(real_cycle_id)
        result = self.calculate_result(
            cycle,
            snapshots,
            duration_seconds=duration,
            interval_seconds=interval,
            status=POST_EXIT_OBSERVER_FAILED if error else POST_EXIT_OBSERVER_COMPLETED,
            error=error,
        )
        self.database.save_real_pilot_post_exit_summary(
            real_cycle_id=real_cycle_id,
            campaign_id=campaign_id,
            started_at=started_at.isoformat(),
            finished_at=now_fn().isoformat(),
            duration_seconds=duration,
            interval_seconds=interval,
            snapshots_count=result.snapshots_count,
            post_exit_mfe=result.post_exit_mfe,
            post_exit_mae=result.post_exit_mae,
            max_price=result.max_price,
            min_price=result.min_price,
            post_exit_target_touched=result.post_exit_target_touched,
            time_to_post_target=result.time_to_post_target,
            closest_distance_after_exit=result.closest_distance_after_exit,
            target_was_reached_before_exit=result.target_was_reached_before_exit,
            target_satisfied_at_observer_start=result.target_satisfied_at_observer_start,
            target_revisited_after_exit=result.target_revisited_after_exit,
            time_to_target_revisit=result.time_to_target_revisit,
            expected_snapshots_count=result.expected_snapshots_count,
            effective_average_interval_seconds=result.effective_average_interval_seconds,
            status=result.status,
            error=result.error,
        )
        return result

    def calculate_result(
        self,
        cycle: dict[str, Any],
        snapshots: list[dict[str, Any]],
        *,
        duration_seconds: float | None = None,
        interval_seconds: float | None = None,
        status: str = POST_EXIT_OBSERVER_COMPLETED,
        error: str | None = None,
    ) -> PostExitObserverResult:
        direction = str(cycle["direction"])
        open_price = _decimal(cycle["open_price"])
        close_price = _decimal(cycle.get("close_price"))
        target_price = self.target_price(direction, open_price)
        prices = [_decimal(row.get("price")) for row in snapshots]
        prices = [price for price in prices if price is not None]
        target_rows = [
            row for row in snapshots
            if _decimal(row.get("price")) is not None
            and self.target_hit(direction, _decimal(row["price"]), target_price)
        ]
        distances = [
            abs(self._distance_to_target(direction, _decimal(row["price"]), target_price))
            for row in snapshots
            if _decimal(row.get("price")) is not None
        ]
        mfe = max((self._directional_move(direction, open_price, price) for price in prices), default=None)
        mae = min((self._directional_move(direction, open_price, price) for price in prices), default=None)
        target_was_reached_before_exit = (
            str(cycle.get("close_reason")) == "real_pilot_target"
            or (close_price is not None and self.target_hit(direction, close_price, target_price))
        )
        target_satisfied_at_observer_start = (
            self.target_hit(direction, prices[0], target_price) if prices else None
        )
        target_revisited_after_exit = bool(target_rows) if snapshots else None
        is_timeout_cycle = str(cycle.get("close_reason")) != "real_pilot_target"
        timestamps = [_parse_time(row.get("timestamp"), fallback=None) for row in snapshots]
        timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
        effective_interval = None
        if len(timestamps) >= 2:
            effective_interval = (timestamps[-1] - timestamps[0]).total_seconds() / (len(timestamps) - 1)
        expected_count = None
        if duration_seconds is not None and interval_seconds is not None and interval_seconds > 0:
            expected_count = int(floor(duration_seconds / interval_seconds)) + 1
        return PostExitObserverResult(
            real_cycle_id=int(cycle["id"]),
            status=status,
            snapshots_count=len(snapshots),
            post_exit_mfe=_float(mfe),
            post_exit_mae=_float(mae),
            max_price=_float(max(prices)) if prices else None,
            min_price=_float(min(prices)) if prices else None,
            post_exit_target_touched=(bool(target_rows) if snapshots else None) if is_timeout_cycle else None,
            time_to_post_target=float(target_rows[0]["seconds_after_exit"]) if target_rows else None,
            closest_distance_after_exit=_float(min(distances)) if distances else None,
            target_was_reached_before_exit=target_was_reached_before_exit,
            target_satisfied_at_observer_start=target_satisfied_at_observer_start,
            target_revisited_after_exit=target_revisited_after_exit,
            time_to_target_revisit=float(target_rows[0]["seconds_after_exit"]) if target_rows else None,
            expected_snapshots_count=expected_count,
            effective_average_interval_seconds=effective_interval,
            error=error,
        )

    def _store_terminal_summary(
        self,
        *,
        real_cycle_id: int,
        campaign_id: str | None,
        started_at: str,
        duration_seconds: float,
        interval_seconds: float,
        status: str,
        error: str | None,
    ) -> PostExitObserverResult:
        self.database.save_real_pilot_post_exit_summary(
            real_cycle_id=real_cycle_id,
            campaign_id=campaign_id,
            started_at=started_at,
            finished_at=datetime.utcnow().isoformat(),
            duration_seconds=duration_seconds,
            interval_seconds=interval_seconds,
            snapshots_count=0,
            post_exit_mfe=None,
            post_exit_mae=None,
            max_price=None,
            min_price=None,
            post_exit_target_touched=None,
            time_to_post_target=None,
            closest_distance_after_exit=None,
            target_was_reached_before_exit=None,
            target_satisfied_at_observer_start=None,
            target_revisited_after_exit=None,
            time_to_target_revisit=None,
            expected_snapshots_count=None,
            effective_average_interval_seconds=None,
            status=status,
            error=error,
        )
        return PostExitObserverResult(
            real_cycle_id=real_cycle_id,
            status=status,
            snapshots_count=0,
            post_exit_mfe=None,
            post_exit_mae=None,
            max_price=None,
            min_price=None,
            post_exit_target_touched=None,
            time_to_post_target=None,
            closest_distance_after_exit=None,
            target_was_reached_before_exit=None,
            target_satisfied_at_observer_start=None,
            target_revisited_after_exit=None,
            time_to_target_revisit=None,
            expected_snapshots_count=None,
            effective_average_interval_seconds=None,
            error=error,
        )

    def _campaign_id(self, real_cycle_id: int) -> str | None:
        snapshots = self.database.load_real_pilot_market_snapshots(real_cycle_id)
        for snapshot in snapshots:
            if snapshot.get("campaign_id"):
                return str(snapshot["campaign_id"])
        return None

    def _latest_short_center(self, real_cycle_id: int) -> Decimal | None:
        snapshots = self.database.load_real_pilot_market_snapshots(real_cycle_id)
        for snapshot in reversed(snapshots):
            center = _decimal(snapshot.get("short_center"))
            if center is not None:
                return center
        return None

    @staticmethod
    def target_price(direction: str, open_price: Decimal | float | str) -> Decimal:
        price = _decimal(open_price)
        multiplier = Decimal(str(HF_MICRO_TARGET_PROFIT))
        if direction == "BUY_USDC":
            return (price * (Decimal("1") + multiplier)).quantize(PRICE_QUANTUM)
        return (price * (Decimal("1") - multiplier)).quantize(PRICE_QUANTUM)

    @staticmethod
    def target_hit(direction: str, price: Decimal | None, target_price: Decimal) -> bool:
        if price is None:
            return False
        if direction == "BUY_USDC":
            return price >= target_price
        return price <= target_price

    @staticmethod
    def _directional_move(direction: str, entry_price: Decimal, price: Decimal) -> Decimal:
        if direction == "BUY_USDC":
            return price - entry_price
        return entry_price - price

    @staticmethod
    def _distance_to_target(direction: str, price: Decimal, target_price: Decimal) -> Decimal:
        if direction == "BUY_USDC":
            return target_price - price
        return price - target_price


class HFPostExitObserverLauncher:
    def __init__(self, config: BotConfig, *, cwd: str | Path | None = None) -> None:
        self.config = config
        self.cwd = Path(cwd) if cwd is not None else Path.cwd()

    def start(self, *, profile: str, real_cycle_id: int) -> bool:
        if not self.config.post_exit_observer_enabled:
            return False
        args = [
            sys.executable,
            "manage.py",
            "hf-post-exit-observer-run",
            "--profile",
            profile,
            "--real-cycle-id",
            str(real_cycle_id),
            "--duration-seconds",
            str(self.config.post_exit_observer_duration_seconds),
            "--interval-seconds",
            str(self.config.post_exit_observer_interval_seconds),
        ]
        kwargs: dict[str, Any] = {
            "cwd": str(self.cwd),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(args, **kwargs)
        return True


def _parse_time(value: Any, *, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(PRICE_QUANTUM)
    except Exception:
        return None
