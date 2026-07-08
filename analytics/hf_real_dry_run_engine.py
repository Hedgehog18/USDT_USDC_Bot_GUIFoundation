from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Protocol
from urllib.parse import urlencode

import requests

from analytics.hf_production_readiness_engine import HF_V1_BASELINE_PROFILE, HF_V1_BASELINE_STATUS
from config.config_manager import BotConfig
from market.binance_market_data_provider import BidAsk, BinanceMarketDataError
from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT, SUPPORTED_RUNTIME_STRATEGY_PROFILES


@dataclass(frozen=True)
class ExchangeSymbolRules:
    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    base_precision: int
    quote_precision: int
    min_qty: Decimal
    step_size: Decimal
    min_notional: Decimal
    tick_size: Decimal


@dataclass(frozen=True)
class AccountBalances:
    usdt: Decimal
    usdc: Decimal


class RealDryRunProvider(Protocol):
    def get_bid_ask(self, symbol: str) -> BidAsk:
        ...

    def get_symbol_rules(self, symbol: str) -> ExchangeSymbolRules:
        ...

    def get_account_balances(self) -> AccountBalances:
        ...


@dataclass(frozen=True)
class HFRealDryRunCheck:
    name: str
    ok: bool
    message: str
    warning: str | None = None


@dataclass(frozen=True)
class HFRealDryRunReport:
    profile: str
    status: str
    checks: list[HFRealDryRunCheck]
    warnings: list[str]
    usdt_balance: Decimal | None
    usdc_balance: Decimal | None
    proposed_stake: Decimal | None
    proposed_quantity: Decimal | None
    proposed_quantity_rounded: Decimal | None
    buy_target_price: Decimal | None
    sell_target_price: Decimal | None

    @property
    def ready(self) -> bool:
        return self.status == "READY_FOR_SMALL_REAL_PILOT"

    @property
    def failed_checks(self) -> list[HFRealDryRunCheck]:
        return [check for check in self.checks if not check.ok]


class BinanceRealDryRunProvider:
    """Read-only Binance provider for dry-run exchange/account checks.

    This class intentionally exposes no order methods.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")
        self.timeout = timeout

    def get_bid_ask(self, symbol: str) -> BidAsk:
        data = self._get_public("/api/v3/ticker/bookTicker", {"symbol": symbol})
        return BidAsk(bid=float(data["bidPrice"]), ask=float(data["askPrice"]))

    def get_symbol_rules(self, symbol: str) -> ExchangeSymbolRules:
        data = self._get_public("/api/v3/exchangeInfo", {"symbol": symbol})
        symbols = data.get("symbols", [])
        if not symbols:
            raise BinanceMarketDataError(f"Symbol not found in exchangeInfo: {symbol}")

        item = symbols[0]
        filters = {entry.get("filterType"): entry for entry in item.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        lot_size = filters.get("LOT_SIZE", {})
        notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}

        return ExchangeSymbolRules(
            symbol=str(item.get("symbol", symbol)),
            status=str(item.get("status", "UNKNOWN")),
            base_asset=str(item.get("baseAsset", "")),
            quote_asset=str(item.get("quoteAsset", "")),
            base_precision=int(item.get("baseAssetPrecision", 0)),
            quote_precision=int(item.get("quoteAssetPrecision", 0)),
            min_qty=Decimal(str(lot_size.get("minQty", "0"))),
            step_size=Decimal(str(lot_size.get("stepSize", "0"))),
            min_notional=Decimal(str(notional.get("minNotional", "0"))),
            tick_size=Decimal(str(price_filter.get("tickSize", "0"))),
        )

    def get_account_balances(self) -> AccountBalances:
        if not self.api_key or not self.api_secret:
            raise BinanceMarketDataError(
                "Binance API key/secret not configured. Set BINANCE_API_KEY and BINANCE_API_SECRET for read-only balance checks."
            )

        data = self._get_signed("/api/v3/account", {})
        balances = {
            str(item.get("asset")): Decimal(str(item.get("free", "0")))
            for item in data.get("balances", [])
        }
        return AccountBalances(
            usdt=balances.get("USDT", Decimal("0")),
            usdc=balances.get("USDC", Decimal("0")),
        )

    def _get_public(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BinanceMarketDataError(f"Binance public API error: {exc}") from exc
        return response.json()

    def _get_signed(self, path: str, params: dict[str, Any]) -> Any:
        assert self.api_key is not None
        assert self.api_secret is not None

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
            response = requests.get(
                url,
                params=signed_params,
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BinanceMarketDataError(f"Binance signed API error: {exc}") from exc
        return response.json()


class HFRealDryRunEngine:
    """Diagnostics-only exchange dry-run for the frozen HF v1 baseline."""

    def __init__(
        self,
        config: BotConfig,
        provider: RealDryRunProvider | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or BinanceRealDryRunProvider(base_url=config.binance_base_url)

    def build_report(self, profile: str = HF_V1_BASELINE_PROFILE) -> HFRealDryRunReport:
        checks: list[HFRealDryRunCheck] = [
            self._check_profile(profile),
            self._check_frozen_baseline(profile),
        ]
        warnings: list[str] = []
        balances: AccountBalances | None = None
        rules: ExchangeSymbolRules | None = None
        bid_ask: BidAsk | None = None

        try:
            bid_ask = self.provider.get_bid_ask(self.config.symbol)
            spread_warning = None
            if bid_ask.spread > self.config.max_allowed_spread:
                spread_warning = (
                    f"spread {bid_ask.spread:.8f} exceeds configured max_allowed_spread {self.config.max_allowed_spread:.8f}"
                )
                warnings.append(spread_warning)
            checks.append(HFRealDryRunCheck(
                "current_price_bid_ask",
                bid_ask.bid > 0 and bid_ask.ask > 0,
                f"bid={bid_ask.bid:.8f}, ask={bid_ask.ask:.8f}, mid={bid_ask.mid_price:.8f}, spread={bid_ask.spread:.8f}",
                spread_warning,
            ))
        except Exception as exc:
            checks.append(HFRealDryRunCheck("current_price_bid_ask", False, f"price/bid/ask unavailable: {exc}"))

        try:
            balances = self.provider.get_account_balances()
            checks.append(HFRealDryRunCheck(
                "account_balances_readable",
                True,
                f"USDT={balances.usdt:.8f}, USDC={balances.usdc:.8f}",
            ))
        except Exception as exc:
            checks.append(HFRealDryRunCheck("account_balances_readable", False, f"account balances unavailable: {exc}"))

        try:
            rules = self.provider.get_symbol_rules(self.config.symbol)
            checks.extend(self._symbol_rule_checks(rules))
        except Exception as exc:
            checks.append(HFRealDryRunCheck("symbol_rules_readable", False, f"symbol rules unavailable: {exc}"))

        proposed_stake = None
        proposed_quantity = None
        proposed_quantity_rounded = None
        buy_target = None
        sell_target = None
        if balances is not None and rules is not None and bid_ask is not None:
            sizing_checks, sizing_warnings, proposed = self._sizing_checks(balances, rules, bid_ask)
            checks.extend(sizing_checks)
            warnings.extend(sizing_warnings)
            proposed_stake, proposed_quantity, proposed_quantity_rounded, buy_target, sell_target = proposed

        mode_ok = self.config.mode.upper() != "REAL"
        mode_warning = None if mode_ok else "real trading mode is enabled unexpectedly"
        if mode_warning:
            warnings.append(mode_warning)
        checks.append(HFRealDryRunCheck(
            "real_trading_disabled",
            mode_ok,
            f"config.mode={self.config.mode}",
            mode_warning,
        ))
        checks.append(HFRealDryRunCheck(
            "no_orders_created",
            True,
            "dry-run uses only read-only account, exchangeInfo, and ticker endpoints; no order endpoint is called",
        ))

        status = "READY_FOR_SMALL_REAL_PILOT" if all(check.ok for check in checks) else "NOT_READY"
        return HFRealDryRunReport(
            profile=profile,
            status=status,
            checks=checks,
            warnings=warnings,
            usdt_balance=balances.usdt if balances else None,
            usdc_balance=balances.usdc if balances else None,
            proposed_stake=proposed_stake,
            proposed_quantity=proposed_quantity,
            proposed_quantity_rounded=proposed_quantity_rounded,
            buy_target_price=buy_target,
            sell_target_price=sell_target,
        )

    @staticmethod
    def _check_profile(profile: str) -> HFRealDryRunCheck:
        ok = profile in SUPPORTED_RUNTIME_STRATEGY_PROFILES
        return HFRealDryRunCheck(
            "profile_exists",
            ok,
            f"profile {profile} is supported" if ok else f"profile {profile} is not supported",
        )

    @staticmethod
    def _check_frozen_baseline(profile: str) -> HFRealDryRunCheck:
        ok = profile == HF_V1_BASELINE_PROFILE
        return HFRealDryRunCheck(
            "frozen_baseline",
            ok,
            f"{profile} status is {HF_V1_BASELINE_STATUS}" if ok else f"{profile} is not HF v1 frozen baseline",
        )

    def _symbol_rule_checks(self, rules: ExchangeSymbolRules) -> list[HFRealDryRunCheck]:
        return [
            HFRealDryRunCheck("symbol_exists", rules.symbol == self.config.symbol, f"symbol={rules.symbol}"),
            HFRealDryRunCheck("symbol_status_trading", rules.status == "TRADING", f"status={rules.status}"),
            HFRealDryRunCheck(
                "base_quote_precision",
                rules.base_precision > 0 and rules.quote_precision > 0,
                f"base={rules.base_asset} precision={rules.base_precision}, quote={rules.quote_asset} precision={rules.quote_precision}",
            ),
            HFRealDryRunCheck("min_qty_readable", rules.min_qty > 0, f"minQty={rules.min_qty}"),
            HFRealDryRunCheck("step_size_readable", rules.step_size > 0, f"stepSize={rules.step_size}"),
            HFRealDryRunCheck("min_notional_readable", rules.min_notional > 0, f"minNotional={rules.min_notional}"),
            HFRealDryRunCheck("tick_size_readable", rules.tick_size > 0, f"tickSize={rules.tick_size}"),
        ]

    def _sizing_checks(
        self,
        balances: AccountBalances,
        rules: ExchangeSymbolRules,
        bid_ask: BidAsk,
    ) -> tuple[list[HFRealDryRunCheck], list[str], tuple[Decimal, Decimal, Decimal, Decimal, Decimal]]:
        warnings: list[str] = []
        checks: list[HFRealDryRunCheck] = []
        mid = Decimal(str(bid_ask.mid_price))
        usdc_value = balances.usdc * mid
        available_stake_base = min(balances.usdt, usdc_value)
        proposed_stake = self._round_decimal(
            available_stake_base * Decimal(str(self.config.trade_size_percent)),
            Decimal("0.00000001"),
        )
        proposed_quantity = proposed_stake / mid if mid > 0 else Decimal("0")
        proposed_quantity_rounded = self._round_decimal(proposed_quantity, rules.step_size)
        rounded_notional = proposed_quantity_rounded * mid
        raw_buy_target = mid * (Decimal("1") + Decimal(str(HF_MICRO_TARGET_PROFIT)))
        raw_sell_target = mid * (Decimal("1") - Decimal(str(HF_MICRO_TARGET_PROFIT)))
        buy_target = self._round_up_decimal(raw_buy_target, rules.tick_size)
        sell_target = self._round_decimal(raw_sell_target, rules.tick_size)
        current_rounded = self._round_decimal(mid, rules.tick_size)

        if balances.usdt < rules.min_notional:
            warnings.append(f"USDT balance {balances.usdt:.8f} is below minNotional {rules.min_notional}")
        if usdc_value < rules.min_notional:
            warnings.append(f"USDC value {usdc_value:.8f} is below minNotional {rules.min_notional}")

        checks.append(HFRealDryRunCheck(
            "usdt_balance",
            balances.usdt > 0,
            f"USDT={balances.usdt:.8f}",
            None if balances.usdt >= rules.min_notional else "USDT balance below minNotional",
        ))
        checks.append(HFRealDryRunCheck(
            "usdc_balance",
            balances.usdc > 0,
            f"USDC={balances.usdc:.8f} value={usdc_value:.8f}",
            None if usdc_value >= rules.min_notional else "USDC value below minNotional",
        ))
        checks.append(HFRealDryRunCheck(
            "proposed_stake_min_notional",
            proposed_stake >= rules.min_notional,
            f"stake={proposed_stake:.8f}, minNotional={rules.min_notional}",
            None if proposed_stake >= rules.min_notional else "proposed stake is below minNotional",
        ))
        checks.append(HFRealDryRunCheck(
            "proposed_quantity_step_size",
            proposed_quantity_rounded >= rules.min_qty and rounded_notional >= rules.min_notional,
            (
                f"quantity={proposed_quantity:.8f}, rounded={proposed_quantity_rounded:.8f}, "
                f"minQty={rules.min_qty}, notional={rounded_notional:.8f}"
            ),
            None if proposed_quantity == proposed_quantity_rounded else "quantity rounding changes proposed order size",
        ))
        target_ok = buy_target > current_rounded and sell_target < current_rounded
        target_warning = None
        if not target_ok:
            target_warning = "target price collapses to current tick after rounding"
        elif buy_target != raw_buy_target or sell_target != raw_sell_target:
            target_warning = "target price requires exchange tick normalization"
        if target_warning:
            warnings.append(target_warning)
        checks.append(HFRealDryRunCheck(
            "target_price_tick_size",
            target_ok,
            f"current_tick={current_rounded}, buy_target={buy_target}, sell_target={sell_target}, tickSize={rules.tick_size}",
            target_warning,
        ))
        return checks, warnings, (proposed_stake, proposed_quantity, proposed_quantity_rounded, buy_target, sell_target)

    @staticmethod
    def _round_decimal(value: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

    @staticmethod
    def _round_up_decimal(value: Decimal, step: Decimal) -> Decimal:
        if step <= 0:
            return value
        rounded_down = HFRealDryRunEngine._round_decimal(value, step)
        if rounded_down == value:
            return rounded_down
        return rounded_down + step
