from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlencode

import requests

from analytics.hf_production_readiness_engine import HF_V1_BASELINE_PROFILE
from analytics.hf_real_dry_run_engine import (
    BinanceRealDryRunProvider,
    HFRealDryRunEngine,
    RealDryRunProvider,
)
from config.config_manager import BotConfig
from market.binance_market_data_provider import BinanceMarketDataError
from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT
from storage.database_manager import DatabaseManager


REAL_PILOT_READY = "READY_FOR_REAL_PILOT"
REAL_PILOT_REFUSED = "REFUSED"
REAL_PILOT_NOT_READY = "NOT_READY"
REAL_PILOT_ARMED_WAITING = "ARMED_WAITING_FOR_SIGNAL"
REAL_PILOT_ORDER_PLACED = "ORDER_PLACED"
REAL_PILOT_HALTED = "HALTED"
REAL_PILOT_ARMED_NO_SIGNAL = "ARMED_NO_SIGNAL"
REAL_PILOT_CLOSE_ARMED_NO_CONDITION = "ARMED_NO_CLOSE_CONDITION"
REAL_PILOT_CLOSE_ORDER_PLACED = "CLOSE_ORDER_PLACED"
REAL_PILOT_NO_OPEN_CYCLE = "NO_OPEN_REAL_CYCLE"

REAL_PILOT_DAILY_LOSS_LIMIT = Decimal("-1.00")
REAL_PILOT_MAX_CONSECUTIVE_LOSSES = 3
REAL_PILOT_DEFAULT_MAX_CYCLES_PER_RUN = 1
REAL_PILOT_MAX_HOLDING_SECONDS = 270.0


@dataclass(frozen=True)
class RealPilotCheck:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class RealOrderResult:
    order_id: str
    status: str
    executed_qty: Decimal
    avg_price: Decimal
    raw_response: dict[str, Any]


class RealPilotOrderClient(RealDryRunProvider, Protocol):
    def create_market_order(self, *, symbol: str, side: str, quantity: Decimal) -> RealOrderResult:
        ...

    def get_account_permissions(self) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class HFRealPilotReport:
    profile: str
    status: str
    run_id: str
    checks: list[RealPilotCheck]
    dry_run_status: str | None
    order_attempted: bool
    order_status: str | None
    real_cycle_id: int | None
    message: str

    @property
    def failed_checks(self) -> list[RealPilotCheck]:
        return [check for check in self.checks if not check.ok]


@dataclass(frozen=True)
class HFRealPilotStatusReport:
    profile: str
    status: str
    open_cycles: int
    closed_cycles: int
    net_profit: float
    losing_cycles: int
    order_events: int
    emergency_stop: bool
    open_cycle_details: "HFRealPilotOpenCycleDetails | None" = None


@dataclass(frozen=True)
class HFRealPilotOpenCycleDetails:
    db_id: int
    direction: str
    open_price: Decimal
    target_price: Decimal
    quantity: Decimal
    opened_at: str
    age_seconds: float
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    distance_to_target: Decimal | None


@dataclass(frozen=True)
class HFRealPilotSignalSnapshot:
    price: float | None
    short_center: float | None
    hf_entry_mode: str
    candidate: bool
    entry_signal: str | None
    block_reason: str


@dataclass(frozen=True)
class HFRealPilotWatchUpdate:
    update_number: int
    signal: HFRealPilotSignalSnapshot
    safety_status: str
    open_real_cycles: int
    order_attempted: bool


@dataclass(frozen=True)
class HFRealPilotWatchReport:
    profile: str
    status: str
    iterations: int
    order_attempted: bool
    final_pilot_report: HFRealPilotReport | None
    updates: list[HFRealPilotWatchUpdate]


@dataclass(frozen=True)
class HFRealPilotCloseUpdate:
    update_number: int
    current_price: Decimal | None
    target_price: Decimal | None
    close_condition_met: bool
    timeout_condition_met: bool
    close_reason: str | None
    age_seconds: float | None
    distance_to_target: Decimal | None
    unrealized_pnl: Decimal | None
    order_attempted: bool


@dataclass(frozen=True)
class HFRealPilotCloseWatchReport:
    profile: str
    status: str
    iterations: int
    order_attempted: bool
    order_status: str | None
    real_cycle_id: int | None
    close_reason: str | None
    message: str
    checks: list[RealPilotCheck]
    updates: list[HFRealPilotCloseUpdate]

    @property
    def failed_checks(self) -> list[RealPilotCheck]:
        return [check for check in self.checks if not check.ok]


class BinanceRealPilotOrderClient(BinanceRealDryRunProvider):
    """Spot-only Binance client used by the explicitly confirmed real pilot command."""

    def get_account_permissions(self) -> dict[str, Any]:
        return self._get_signed("/api/v3/account", {})

    def create_market_order(self, *, symbol: str, side: str, quantity: Decimal) -> RealOrderResult:
        data = self._post_signed(
            "/api/v3/order",
            {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": f"{quantity:f}",
                "newOrderRespType": "FULL",
            },
        )
        executed_qty = Decimal(str(data.get("executedQty", "0")))
        fills = data.get("fills", []) or []
        if fills:
            total_qty = sum(Decimal(str(fill.get("qty", "0"))) for fill in fills)
            total_notional = sum(
                Decimal(str(fill.get("qty", "0"))) * Decimal(str(fill.get("price", "0")))
                for fill in fills
            )
            avg_price = total_notional / total_qty if total_qty > 0 else Decimal("0")
        else:
            avg_price = Decimal(str(data.get("price", "0")))
        return RealOrderResult(
            order_id=str(data.get("orderId", "")),
            status=str(data.get("status", "UNKNOWN")),
            executed_qty=executed_qty,
            avg_price=avg_price,
            raw_response=data,
        )

    def _post_signed(self, path: str, params: dict[str, Any]) -> Any:
        if not self.api_key or not self.api_secret:
            raise BinanceMarketDataError("Binance API key/secret not configured for real pilot order client.")
        signed_params = dict(params)
        signed_params["timestamp"] = int(time.time() * 1000)
        signed_params["recvWindow"] = 5000
        query = urlencode(signed_params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed_params["signature"] = signature
        url = f"{self.base_url}{path}"
        try:
            response = requests.post(
                url,
                params=signed_params,
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BinanceMarketDataError(f"Binance real pilot order API error: {exc}") from exc
        return response.json()


class HFRealPilotEngine:
    def __init__(
        self,
        database: DatabaseManager,
        config: BotConfig,
        order_client: RealPilotOrderClient | None = None,
        emergency_stop_path: str | Path = "EMERGENCY_STOP",
    ) -> None:
        self.database = database
        self.config = config
        self.order_client = order_client or BinanceRealPilotOrderClient(base_url=config.binance_base_url)
        self.emergency_stop_path = Path(emergency_stop_path)

    def run_once(
        self,
        *,
        profile: str,
        pilot_stake: Decimal,
        confirmed: bool,
        max_cycles_per_run: int = REAL_PILOT_DEFAULT_MAX_CYCLES_PER_RUN,
        entry_signal: str | None = None,
    ) -> HFRealPilotReport:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        early_checks = [
            RealPilotCheck("profile_allowed", profile == HF_V1_BASELINE_PROFILE, f"profile={profile}"),
            RealPilotCheck("explicit_confirmation", confirmed, "requires --confirm-real-pilot"),
        ]
        if not all(check.ok for check in early_checks):
            return HFRealPilotReport(
                profile=profile,
                status=REAL_PILOT_REFUSED,
                run_id=run_id,
                checks=early_checks,
                dry_run_status=None,
                order_attempted=False,
                order_status=None,
                real_cycle_id=None,
                message="Real pilot refused before exchange checks; explicit confirmation and HF v1 profile are required.",
            )

        checks = self._preflight_checks(
            profile=profile,
            pilot_stake=pilot_stake,
            confirmed=confirmed,
            max_cycles_per_run=max_cycles_per_run,
        )
        dry_run_status = self._dry_run_status(profile, pilot_stake)
        checks.append(RealPilotCheck(
            "dry_run_ready",
            dry_run_status == "READY_FOR_SMALL_REAL_PILOT",
            f"hf-real-dry-run status={dry_run_status}",
        ))

        if not all(check.ok for check in checks):
            refused = any(check.name in {"explicit_confirmation", "profile_allowed"} and not check.ok for check in checks)
            return HFRealPilotReport(
                profile=profile,
                status=REAL_PILOT_REFUSED if refused else REAL_PILOT_NOT_READY,
                run_id=run_id,
                checks=checks,
                dry_run_status=dry_run_status,
                order_attempted=False,
                order_status=None,
                real_cycle_id=None,
                message="Real pilot did not start; safety gates failed.",
            )

        if entry_signal not in {"BUY_USDC", "SELL_USDC"}:
            return HFRealPilotReport(
                profile=profile,
                status=REAL_PILOT_ARMED_WAITING,
                run_id=run_id,
                checks=checks,
                dry_run_status=dry_run_status,
                order_attempted=False,
                order_status=None,
                real_cycle_id=None,
                message="Real pilot armed; no HF entry signal supplied for this iteration.",
            )

        return self._place_entry_order(
            run_id=run_id,
            profile=profile,
            pilot_stake=pilot_stake,
            direction=entry_signal,
            checks=checks,
            dry_run_status=dry_run_status,
        )

    def watch(
        self,
        *,
        profile: str,
        pilot_stake: Decimal,
        confirmed: bool,
        max_iterations: int,
        interval_seconds: float,
        signal_provider: Callable[[], HFRealPilotSignalSnapshot],
        sleep_fn: Callable[[float], None] = time.sleep,
        update_callback: Callable[[HFRealPilotWatchUpdate], None] | None = None,
    ) -> HFRealPilotWatchReport:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be greater than 0.")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be 0 or greater.")

        early = self.run_once(
            profile=profile,
            pilot_stake=pilot_stake,
            confirmed=confirmed,
            entry_signal=None,
        )
        if early.status in {REAL_PILOT_REFUSED, REAL_PILOT_NOT_READY}:
            return HFRealPilotWatchReport(
                profile=profile,
                status=early.status,
                iterations=0,
                order_attempted=False,
                final_pilot_report=early,
                updates=[],
            )

        updates: list[HFRealPilotWatchUpdate] = []
        final_report: HFRealPilotReport | None = early
        for index in range(1, max_iterations + 1):
            signal = signal_provider()
            entry_signal = signal.entry_signal if signal.candidate else None
            final_report = self.run_once(
                profile=profile,
                pilot_stake=pilot_stake,
                confirmed=confirmed,
                entry_signal=entry_signal,
            )
            update = HFRealPilotWatchUpdate(
                update_number=index,
                signal=signal,
                safety_status=final_report.status,
                open_real_cycles=self.database.count_open_real_pilot_cycles(profile),
                order_attempted=final_report.order_attempted,
            )
            updates.append(update)
            if update_callback is not None:
                update_callback(update)

            if final_report.order_attempted:
                return HFRealPilotWatchReport(
                    profile=profile,
                    status=final_report.status,
                    iterations=index,
                    order_attempted=True,
                    final_pilot_report=final_report,
                    updates=updates,
                )
            if final_report.status in {REAL_PILOT_REFUSED, REAL_PILOT_NOT_READY, REAL_PILOT_HALTED}:
                return HFRealPilotWatchReport(
                    profile=profile,
                    status=final_report.status,
                    iterations=index,
                    order_attempted=final_report.order_attempted,
                    final_pilot_report=final_report,
                    updates=updates,
                )
            if index < max_iterations:
                sleep_fn(interval_seconds)

        return HFRealPilotWatchReport(
            profile=profile,
            status=REAL_PILOT_ARMED_NO_SIGNAL,
            iterations=max_iterations,
            order_attempted=False,
            final_pilot_report=final_report,
            updates=updates,
        )

    def close_watch(
        self,
        *,
        profile: str,
        confirmed: bool,
        max_iterations: int,
        interval_seconds: float,
        sleep_fn: Callable[[float], None] = time.sleep,
        update_callback: Callable[[HFRealPilotCloseUpdate], None] | None = None,
    ) -> HFRealPilotCloseWatchReport:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be greater than 0.")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be 0 or greater.")

        checks = self._close_preflight_checks(profile=profile, confirmed=confirmed)
        if not all(check.ok for check in checks):
            status = REAL_PILOT_REFUSED if any(
                check.name in {"explicit_confirmation", "profile_allowed"} and not check.ok
                for check in checks
            ) else REAL_PILOT_NOT_READY
            if any(check.name == "open_real_cycle_exists" and not check.ok for check in checks):
                status = REAL_PILOT_NO_OPEN_CYCLE
            return HFRealPilotCloseWatchReport(
                profile=profile,
                status=status,
                iterations=0,
                order_attempted=False,
                order_status=None,
                real_cycle_id=None,
                close_reason=None,
                message="Real pilot close watcher did not start; close safety gates failed.",
                checks=checks,
                updates=[],
            )

        updates: list[HFRealPilotCloseUpdate] = []
        for index in range(1, max_iterations + 1):
            cycle = self.database.load_open_real_pilot_cycle(profile)
            if cycle is None:
                return HFRealPilotCloseWatchReport(
                    profile=profile,
                    status=REAL_PILOT_NO_OPEN_CYCLE,
                    iterations=index - 1,
                    order_attempted=False,
                    order_status=None,
                    real_cycle_id=None,
                    close_reason=None,
                    message="No open real pilot cycle remains to close.",
                    checks=checks,
                    updates=updates,
                )

            update = self._build_close_update(index, cycle)
            updates.append(update)
            if update_callback is not None:
                update_callback(update)

            if update.close_reason is not None:
                return self._place_close_order(
                    profile=profile,
                    cycle=cycle,
                    close_reason=update.close_reason,
                    checks=checks,
                    updates=updates,
                )
            if index < max_iterations:
                sleep_fn(interval_seconds)

        return HFRealPilotCloseWatchReport(
            profile=profile,
            status=REAL_PILOT_ARMED_NO_SIGNAL,
            iterations=max_iterations,
            order_attempted=False,
            order_status=None,
            real_cycle_id=None,
            close_reason=None,
            message="Close watcher finished without target, timeout, or safety close condition.",
            checks=checks,
            updates=updates,
        )

    def build_status(self, profile: str) -> HFRealPilotStatusReport:
        stats = self.database.load_real_pilot_status(profile)
        blocked = self.emergency_stop_path.exists()
        status = "EMERGENCY_STOP" if blocked else "READY"
        if int(stats["open_cycles"]) > 0:
            status = "OPEN_REAL_CYCLE"
        open_cycle_details = self._build_open_cycle_details(profile)
        return HFRealPilotStatusReport(
            profile=profile,
            status=status,
            open_cycles=int(stats["open_cycles"]),
            closed_cycles=int(stats["closed_cycles"]),
            net_profit=float(stats["net_profit"]),
            losing_cycles=int(stats["losing_cycles"]),
            order_events=int(stats["order_events"]),
            emergency_stop=blocked,
            open_cycle_details=open_cycle_details,
        )

    def _close_preflight_checks(self, *, profile: str, confirmed: bool) -> list[RealPilotCheck]:
        open_cycles = self.database.count_open_real_pilot_cycles(profile)
        checks = [
            RealPilotCheck("profile_allowed", profile == HF_V1_BASELINE_PROFILE, f"profile={profile}"),
            RealPilotCheck("explicit_confirmation", confirmed, "requires --confirm-real-pilot"),
            RealPilotCheck("spot_symbol_only", self.config.symbol == "USDCUSDT", f"symbol={self.config.symbol}"),
            RealPilotCheck("open_real_cycle_exists", open_cycles == 1, f"open_real_cycles={open_cycles}"),
            self._permissions_check(),
        ]
        cycle = self.database.load_open_real_pilot_cycle(profile)
        if cycle is not None:
            dry_run_status = self._dry_run_status(profile, Decimal(str(cycle["stake_usdt"])))
            checks.append(RealPilotCheck(
                "dry_run_ready",
                dry_run_status == "READY_FOR_SMALL_REAL_PILOT",
                f"hf-real-dry-run status={dry_run_status}",
            ))
        return checks

    def _build_open_cycle_details(self, profile: str) -> HFRealPilotOpenCycleDetails | None:
        cycle = self.database.load_open_real_pilot_cycle(profile)
        if cycle is None:
            return None
        try:
            bid_ask = self.order_client.get_bid_ask(self.config.symbol)
            current_price = self._executable_close_price(cycle["direction"], bid_ask)
            unrealized = self._profit_for_cycle(cycle, current_price)
            distance = self._distance_to_target(cycle["direction"], current_price, self._target_price(cycle))
        except Exception:
            current_price = None
            unrealized = None
            distance = None
        return HFRealPilotOpenCycleDetails(
            db_id=int(cycle["id"]),
            direction=str(cycle["direction"]),
            open_price=Decimal(str(cycle["open_price"])),
            target_price=self._target_price(cycle),
            quantity=Decimal(str(cycle["quantity"])),
            opened_at=str(cycle["opened_at"]),
            age_seconds=self._cycle_age_seconds(cycle),
            current_price=current_price,
            unrealized_pnl=unrealized,
            distance_to_target=distance,
        )

    def _build_close_update(self, update_number: int, cycle: dict) -> HFRealPilotCloseUpdate:
        target_price = self._target_price(cycle)
        age_seconds = self._cycle_age_seconds(cycle)
        try:
            bid_ask = self.order_client.get_bid_ask(self.config.symbol)
            current_price = self._executable_close_price(cycle["direction"], bid_ask)
            unrealized = self._profit_for_cycle(cycle, current_price)
            distance = self._distance_to_target(cycle["direction"], current_price, target_price)
            close_condition_met = self._close_condition_met(cycle["direction"], current_price, target_price)
        except Exception:
            current_price = None
            unrealized = None
            distance = None
            close_condition_met = False

        timeout_condition_met = age_seconds >= REAL_PILOT_MAX_HOLDING_SECONDS
        close_reason = None
        if current_price is not None:
            if close_condition_met:
                close_reason = "real_pilot_target"
            elif timeout_condition_met:
                close_reason = "max_holding_270s"
            elif self.emergency_stop_path.exists():
                close_reason = "real_pilot_safety_stop"

        return HFRealPilotCloseUpdate(
            update_number=update_number,
            current_price=current_price,
            target_price=target_price,
            close_condition_met=close_condition_met,
            timeout_condition_met=timeout_condition_met,
            close_reason=close_reason,
            age_seconds=age_seconds,
            distance_to_target=distance,
            unrealized_pnl=unrealized,
            order_attempted=False,
        )

    def _place_close_order(
        self,
        *,
        profile: str,
        cycle: dict,
        close_reason: str,
        checks: list[RealPilotCheck],
        updates: list[HFRealPilotCloseUpdate],
    ) -> HFRealPilotCloseWatchReport:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        quantity = Decimal(str(cycle["quantity"]))
        side = "SELL" if cycle["direction"] == "BUY_USDC" else "BUY"
        request_payload = {
            "symbol": self.config.symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{quantity:f}",
            "close_cycle_id": cycle["id"],
            "close_reason": close_reason,
        }
        try:
            self.database.save_real_pilot_order_event(
                run_id=run_id,
                strategy_profile=profile,
                symbol=self.config.symbol,
                side=side,
                quantity=float(quantity),
                status="ATTEMPTED_CLOSE",
                request_payload=json.dumps(request_payload, sort_keys=True),
                response_payload="{}",
            )
            result = self.order_client.create_market_order(symbol=self.config.symbol, side=side, quantity=quantity)
            self.database.save_real_pilot_order_event(
                run_id=run_id,
                strategy_profile=profile,
                symbol=self.config.symbol,
                side=side,
                quantity=float(quantity),
                status=result.status,
                request_payload=json.dumps(request_payload, sort_keys=True),
                response_payload=json.dumps(result.raw_response, sort_keys=True),
            )
        except Exception as exc:
            self.database.save_real_pilot_order_event(
                run_id=run_id,
                strategy_profile=profile,
                symbol=self.config.symbol,
                side=side,
                quantity=float(quantity),
                status="FAILED_CLOSE",
                request_payload=json.dumps(request_payload, sort_keys=True),
                response_payload="{}",
                error=str(exc),
            )
            return HFRealPilotCloseWatchReport(
                profile=profile,
                status=REAL_PILOT_HALTED,
                iterations=len(updates),
                order_attempted=True,
                order_status="FAILED",
                real_cycle_id=int(cycle["id"]),
                close_reason=close_reason,
                message=f"Close order failed/unknown; pilot halted: {exc}",
                checks=checks,
                updates=updates,
            )

        if result.status != "FILLED" or result.executed_qty <= 0 or result.avg_price <= 0:
            return HFRealPilotCloseWatchReport(
                profile=profile,
                status=REAL_PILOT_HALTED,
                iterations=len(updates),
                order_attempted=True,
                order_status=result.status,
                real_cycle_id=int(cycle["id"]),
                close_reason=close_reason,
                message="Close order was not fully filled; pilot halted.",
                checks=checks,
                updates=updates,
            )

        pnl = self._profit_for_cycle(cycle, result.avg_price)
        self.database.close_real_pilot_cycle(
            int(cycle["id"]),
            close_price=float(result.avg_price),
            gross_profit=float(pnl),
            net_profit=float(pnl),
            close_reason=close_reason,
        )
        return HFRealPilotCloseWatchReport(
            profile=profile,
            status=REAL_PILOT_CLOSE_ORDER_PLACED,
            iterations=len(updates),
            order_attempted=True,
            order_status=result.status,
            real_cycle_id=int(cycle["id"]),
            close_reason=close_reason,
            message="Real pilot close order filled and cycle closed separately from paper cycles.",
            checks=checks,
            updates=updates,
        )

    def _preflight_checks(
        self,
        *,
        profile: str,
        pilot_stake: Decimal,
        confirmed: bool,
        max_cycles_per_run: int,
    ) -> list[RealPilotCheck]:
        checks = [
            RealPilotCheck("profile_allowed", profile == HF_V1_BASELINE_PROFILE, f"profile={profile}"),
            RealPilotCheck("explicit_confirmation", confirmed, "requires --confirm-real-pilot"),
            RealPilotCheck("spot_symbol_only", self.config.symbol == "USDCUSDT", f"symbol={self.config.symbol}"),
            RealPilotCheck("pilot_stake_positive", pilot_stake > 0, f"pilot_stake={pilot_stake}"),
            RealPilotCheck("max_cycles_per_run", max_cycles_per_run <= REAL_PILOT_DEFAULT_MAX_CYCLES_PER_RUN, f"max_cycles_per_run={max_cycles_per_run}"),
            RealPilotCheck("emergency_stop_clear", not self.emergency_stop_path.exists(), f"path={self.emergency_stop_path}"),
        ]
        open_cycles = self.database.count_open_real_pilot_cycles(profile)
        checks.append(RealPilotCheck("max_one_open_real_cycle", open_cycles == 0, f"open_real_cycles={open_cycles}"))
        checks.extend(self._risk_checks(profile))
        checks.append(self._permissions_check())
        return checks

    def _risk_checks(self, profile: str) -> list[RealPilotCheck]:
        net, losses = self._load_daily_risk(profile)
        return [
            RealPilotCheck("daily_loss_limit", net > REAL_PILOT_DAILY_LOSS_LIMIT, f"today_real_pilot_net={net}, limit={REAL_PILOT_DAILY_LOSS_LIMIT}"),
            RealPilotCheck("max_consecutive_losses", losses < REAL_PILOT_MAX_CONSECUTIVE_LOSSES, f"losses={losses}, limit={REAL_PILOT_MAX_CONSECUTIVE_LOSSES}"),
        ]

    def _load_daily_risk(self, profile: str) -> tuple[Decimal, int]:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(net_profit), 0)
                FROM real_pilot_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'HALTED')
                  AND date(COALESCE(closed_at, timestamp)) = date('now')
                """,
                (profile,),
            ).fetchone()
            recent = conn.execute(
                """
                SELECT net_profit
                FROM real_pilot_cycles
                WHERE strategy_profile = ?
                  AND status IN ('CLOSED', 'HALTED')
                ORDER BY id DESC
                LIMIT 50
                """,
                (profile,),
            ).fetchall()
        consecutive_losses = 0
        for item in recent:
            if Decimal(str(item[0])) < 0:
                consecutive_losses += 1
            else:
                break
        return Decimal(str(row[0] if row else 0)), consecutive_losses

    def _permissions_check(self) -> RealPilotCheck:
        try:
            account = self.order_client.get_account_permissions()
            can_trade = bool(account.get("canTrade", False))
            account_can_withdraw = bool(account.get("canWithdraw", False))
            permissions = {str(item).upper() for item in account.get("permissions", [])}
            account_type = str(account.get("accountType", "")).upper()
            spot_ok = "SPOT" in permissions or account_type == "SPOT"
            ok = can_trade and spot_ok
            return RealPilotCheck(
                "api_permissions_spot_only",
                ok,
                (
                    f"canTrade={can_trade}, accountCanWithdraw={account_can_withdraw}, "
                    f"accountType={account_type or 'N/A'}, permissions={','.join(sorted(permissions)) or 'N/A'}; "
                    "accountCanWithdraw is account-level and is not used as an API-key withdrawal permission gate"
                ),
            )
        except Exception as exc:
            return RealPilotCheck("api_permissions_spot_only", False, f"permissions unavailable: {exc}")

    def _dry_run_status(self, profile: str, pilot_stake: Decimal) -> str:
        report = HFRealDryRunEngine(self.config, self.order_client).build_report_with_stake(
            profile=profile,
            pilot_stake=pilot_stake,
        )
        return report.status

    @staticmethod
    def _target_price(cycle: dict) -> Decimal:
        open_price = Decimal(str(cycle["open_price"]))
        multiplier = Decimal(str(HF_MICRO_TARGET_PROFIT))
        if cycle["direction"] == "BUY_USDC":
            return open_price * (Decimal("1") + multiplier)
        return open_price * (Decimal("1") - multiplier)

    @staticmethod
    def _executable_close_price(direction: str, bid_ask) -> Decimal:
        if direction == "BUY_USDC":
            return Decimal(str(bid_ask.bid))
        return Decimal(str(bid_ask.ask))

    @staticmethod
    def _distance_to_target(direction: str, current_price: Decimal, target_price: Decimal) -> Decimal:
        if direction == "BUY_USDC":
            return target_price - current_price
        return current_price - target_price

    @staticmethod
    def _close_condition_met(direction: str, current_price: Decimal, target_price: Decimal) -> bool:
        if direction == "BUY_USDC":
            return current_price >= target_price
        return current_price <= target_price

    @staticmethod
    def _profit_for_cycle(cycle: dict, close_price: Decimal) -> Decimal:
        open_price = Decimal(str(cycle["open_price"]))
        quantity = Decimal(str(cycle["quantity"]))
        if cycle["direction"] == "BUY_USDC":
            return (close_price - open_price) * quantity
        return (open_price - close_price) * quantity

    @staticmethod
    def _cycle_age_seconds(cycle: dict) -> float:
        opened_raw = str(cycle["opened_at"])
        try:
            opened = datetime.fromisoformat(opened_raw)
        except ValueError:
            return 0.0
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - opened.astimezone(timezone.utc)).total_seconds())

    def _place_entry_order(
        self,
        *,
        run_id: str,
        profile: str,
        pilot_stake: Decimal,
        direction: str,
        checks: list[RealPilotCheck],
        dry_run_status: str,
    ) -> HFRealPilotReport:
        dry_run = HFRealDryRunEngine(self.config, self.order_client).build_report_with_stake(
            profile=profile,
            pilot_stake=pilot_stake,
        )
        quantity = dry_run.proposed_quantity_rounded or Decimal("0")
        side = "BUY" if direction == "BUY_USDC" else "SELL"
        request_payload = {
            "symbol": self.config.symbol,
            "side": side,
            "type": "MARKET",
            "quantity": f"{quantity:f}",
        }
        try:
            self.database.save_real_pilot_order_event(
                run_id=run_id,
                strategy_profile=profile,
                symbol=self.config.symbol,
                side=side,
                quantity=float(quantity),
                status="ATTEMPTED",
                request_payload=json.dumps(request_payload, sort_keys=True),
                response_payload="{}",
            )
            result = self.order_client.create_market_order(symbol=self.config.symbol, side=side, quantity=quantity)
            self.database.save_real_pilot_order_event(
                run_id=run_id,
                strategy_profile=profile,
                symbol=self.config.symbol,
                side=side,
                quantity=float(quantity),
                status=result.status,
                request_payload=json.dumps(request_payload, sort_keys=True),
                response_payload=json.dumps(result.raw_response, sort_keys=True),
            )
        except Exception as exc:
            self.database.save_real_pilot_order_event(
                run_id=run_id,
                strategy_profile=profile,
                symbol=self.config.symbol,
                side=side,
                quantity=float(quantity),
                status="FAILED",
                request_payload=json.dumps(request_payload, sort_keys=True),
                response_payload="{}",
                error=str(exc),
            )
            return HFRealPilotReport(
                profile=profile,
                status=REAL_PILOT_HALTED,
                run_id=run_id,
                checks=checks,
                dry_run_status=dry_run_status,
                order_attempted=True,
                order_status="FAILED",
                real_cycle_id=None,
                message=f"Order failed/unknown; pilot halted: {exc}",
            )

        if result.status != "FILLED" or result.executed_qty <= 0 or result.avg_price <= 0:
            return HFRealPilotReport(
                profile=profile,
                status=REAL_PILOT_HALTED,
                run_id=run_id,
                checks=checks,
                dry_run_status=dry_run_status,
                order_attempted=True,
                order_status=result.status,
                real_cycle_id=None,
                message="Order was not fully filled; pilot halted.",
            )

        cycle_id = self.database.save_real_pilot_cycle(
            run_id=run_id,
            strategy_profile=profile,
            symbol=self.config.symbol,
            direction=direction,
            status="OPEN",
            open_price=float(result.avg_price),
            quantity=float(result.executed_qty),
            stake_usdt=float(pilot_stake),
            exchange_order_id=result.order_id,
        )
        return HFRealPilotReport(
            profile=profile,
            status=REAL_PILOT_ORDER_PLACED,
            run_id=run_id,
            checks=checks,
            dry_run_status=dry_run_status,
            order_attempted=True,
            order_status=result.status,
            real_cycle_id=cycle_id,
            message="Real pilot entry order filled and tracked separately from paper cycles.",
        )
