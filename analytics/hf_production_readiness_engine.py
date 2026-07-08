from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from analytics.profile_performance_summary_engine import (
    ProfilePerformanceSummary,
    ProfilePerformanceSummaryEngine,
)
from config.config_manager import BotConfig
from market.binance_market_data_provider import BinanceMarketDataError, BinanceMarketDataProvider
from paper.models import PaperPortfolio
from paper.paper_safety_engine import HF_SAFETY_PROFILE, PaperSafetyEngine
from strategy.profile_decision_engine import SUPPORTED_RUNTIME_STRATEGY_PROFILES
from storage.database_manager import DatabaseManager


HF_V1_BASELINE_PROFILE = "mean_reversion_hf_micro_v1"
HF_V1_BASELINE_STATUS = "FROZEN BASELINE"


class ReadOnlyMarketProvider(Protocol):
    def get_bid_ask(self, symbol: str):
        ...

    def get_order_book(self, symbol: str, limit: int = 20):
        ...


@dataclass(frozen=True)
class HFProductionReadinessCheck:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class HFProductionReadinessReport:
    profile: str
    status: str
    checks: list[HFProductionReadinessCheck]
    performance_summary: ProfilePerformanceSummary | None

    @property
    def ready(self) -> bool:
        return self.status == "READY_FOR_DRY_RUN"

    @property
    def failed_checks(self) -> list[HFProductionReadinessCheck]:
        return [check for check in self.checks if not check.ok]


class HFProductionReadinessEngine:
    """Diagnostics-only readiness gate for the frozen HF v1 paper baseline."""

    def __init__(
        self,
        database: DatabaseManager,
        config: BotConfig,
        market_provider: ReadOnlyMarketProvider | None = None,
    ) -> None:
        self.database = database
        self.config = config
        self.market_provider = market_provider or BinanceMarketDataProvider(
            base_url=config.binance_base_url,
            timeout=10,
        )

    def build_report(self, profile: str = HF_V1_BASELINE_PROFILE) -> HFProductionReadinessReport:
        performance = self._load_performance(profile)
        checks = [
            self._check_profile(profile),
            self._check_frozen_baseline(profile),
            self._check_no_open_paper_cycles(profile),
            self._check_performance(performance),
            self._check_safety_policy(profile),
            self._check_recovery_clean(profile),
            self._check_binance_connection(),
            self._check_balances_readable(),
            self._check_symbol_rules(),
            self._check_real_trading_disabled(),
            self._check_emergency_stop_available(),
            self._check_directory_writable("logs", Path(self.config.log_file_path).parent),
            self._check_directory_writable("reports", Path("reports")),
        ]
        status = "READY_FOR_DRY_RUN" if all(check.ok for check in checks) else "NOT_READY"
        return HFProductionReadinessReport(
            profile=profile,
            status=status,
            checks=checks,
            performance_summary=performance,
        )

    def _load_performance(self, profile: str) -> ProfilePerformanceSummary | None:
        try:
            return ProfilePerformanceSummaryEngine(self.database).build_summary(profile)
        except Exception:
            return None

    @staticmethod
    def _check_profile(profile: str) -> HFProductionReadinessCheck:
        ok = profile in SUPPORTED_RUNTIME_STRATEGY_PROFILES
        return HFProductionReadinessCheck(
            "profile_exists",
            ok,
            f"profile {profile} is supported" if ok else f"profile {profile} is not supported",
        )

    @staticmethod
    def _check_frozen_baseline(profile: str) -> HFProductionReadinessCheck:
        ok = profile == HF_V1_BASELINE_PROFILE
        return HFProductionReadinessCheck(
            "frozen_baseline",
            ok,
            (
                f"{profile} status is {HF_V1_BASELINE_STATUS}"
                if ok
                else f"{profile} is not the frozen HF v1 baseline"
            ),
        )

    def _check_no_open_paper_cycles(self, profile: str) -> HFProductionReadinessCheck:
        try:
            open_count = self._count_open_cycles(profile)
            return HFProductionReadinessCheck(
                "no_open_paper_cycles",
                open_count == 0,
                f"open paper cycles for profile: {open_count}",
            )
        except Exception as exc:
            return HFProductionReadinessCheck("no_open_paper_cycles", False, f"could not read open cycles: {exc}")

    def _count_open_cycles(self, profile: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM paper_cycles WHERE strategy_profile = ? AND status = 'OPEN'",
                (profile,),
            ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _check_performance(performance: ProfilePerformanceSummary | None) -> HFProductionReadinessCheck:
        if performance is None:
            return HFProductionReadinessCheck("latest_paper_performance", False, "performance summary unavailable")
        ok = performance.automatic_closed_count > 0 and performance.total_realized_net_profit > 0
        return HFProductionReadinessCheck(
            "latest_paper_performance",
            ok,
            (
                f"cycles={performance.total_profile_cycles}, auto_closed={performance.automatic_closed_count}, "
                f"net={performance.total_realized_net_profit:+.8f}, recommendation={performance.recommendation}"
            ),
        )

    def _check_safety_policy(self, profile: str) -> HFProductionReadinessCheck:
        if profile != HF_SAFETY_PROFILE:
            return HFProductionReadinessCheck(
                "safety_policy",
                False,
                f"HF safety policy is only defined for {HF_SAFETY_PROFILE}",
            )

        try:
            result = PaperSafetyEngine(self.config).check_for_profile(
                PaperPortfolio(self.config.backtest_initial_usdt, self.config.backtest_initial_usdc),
                [],
                strategy_profile=profile,
            )
            policy = (result.diagnostics or {}).get("paper_safety_policy")
            return HFProductionReadinessCheck(
                "safety_policy",
                policy == "hf_micro",
                f"paper_safety_policy={policy or 'N/A'}",
            )
        except Exception as exc:
            return HFProductionReadinessCheck("safety_policy", False, f"safety policy unavailable: {exc}")

    def _check_recovery_clean(self, profile: str) -> HFProductionReadinessCheck:
        try:
            with self.database.connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM paper_cycles
                    WHERE strategy_profile = ?
                      AND status = 'OPEN'
                      AND COALESCE(recovery_status, 'ACTIVE') NOT IN ('RESOLVED', 'ABANDONED')
                    """,
                    (profile,),
                ).fetchone()
            unresolved = int(row[0]) if row else 0
            return HFProductionReadinessCheck(
                "recovery_state_clean",
                unresolved == 0,
                f"unresolved recovery/open cycles: {unresolved}",
            )
        except Exception as exc:
            return HFProductionReadinessCheck("recovery_state_clean", False, f"could not read recovery state: {exc}")

    def _check_binance_connection(self) -> HFProductionReadinessCheck:
        try:
            bid_ask = self.market_provider.get_bid_ask(self.config.symbol)
            ok = bid_ask.bid > 0 and bid_ask.ask > 0
            return HFProductionReadinessCheck(
                "binance_connection",
                ok,
                f"bid={bid_ask.bid:.8f}, ask={bid_ask.ask:.8f}" if ok else "invalid Binance bid/ask",
            )
        except BinanceMarketDataError as exc:
            return HFProductionReadinessCheck("binance_connection", False, str(exc))
        except Exception as exc:
            return HFProductionReadinessCheck("binance_connection", False, f"Binance check failed: {exc}")

    def _check_balances_readable(self) -> HFProductionReadinessCheck:
        usdt = self.config.backtest_initial_usdt
        usdc = self.config.backtest_initial_usdc
        ok = usdt >= 0 and usdc >= 0
        return HFProductionReadinessCheck(
            "balances_readable",
            ok,
            (
                f"paper/config balances readable: USDT={usdt:.8f}, USDC={usdc:.8f}; "
                "no authenticated real-account balance call is made"
            ),
        )

    def _check_symbol_rules(self) -> HFProductionReadinessCheck:
        try:
            order_book = self.market_provider.get_order_book(self.config.symbol, limit=5)
            has_market_depth = bool(order_book.bids and order_book.asks)
            local_rules_ok = (
                self.config.price_tick_size > 0
                and self.config.quantity_step_size > 0
                and self.config.min_notional > 0
            )
            ok = has_market_depth and local_rules_ok
            return HFProductionReadinessCheck(
                "symbol_precision_min_notional",
                ok,
                (
                    f"price_tick={self.config.price_tick_size}, qty_step={self.config.quantity_step_size}, "
                    f"min_notional={self.config.min_notional}, order_book_depth={'yes' if has_market_depth else 'no'}"
                ),
            )
        except Exception as exc:
            return HFProductionReadinessCheck("symbol_precision_min_notional", False, f"symbol rules check failed: {exc}")

    def _check_real_trading_disabled(self) -> HFProductionReadinessCheck:
        ok = self.config.mode.upper() != "REAL"
        return HFProductionReadinessCheck(
            "real_trading_disabled",
            ok,
            f"config.mode={self.config.mode}",
        )

    @staticmethod
    def _check_emergency_stop_available() -> HFProductionReadinessCheck:
        return HFProductionReadinessCheck(
            "emergency_stop_available",
            True,
            "paper safe-stop/recovery commands are available; no real order path is enabled",
        )

    @staticmethod
    def _check_directory_writable(name: str, path: Path) -> HFProductionReadinessCheck:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".readiness_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return HFProductionReadinessCheck(f"{name}_directory_writable", True, f"{path} writable")
        except Exception as exc:
            return HFProductionReadinessCheck(f"{name}_directory_writable", False, f"{path} not writable: {exc}")
