from __future__ import annotations

from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine
from trading.fee_rate_provider import FeeRateProvider, FeeRates


DEFAULT_TARGET_PROFIT_VALUES = (
    0.00005,
    0.00010,
    0.00015,
    0.00020,
    0.00025,
    0.00030,
)

SUPPORTED_TARGET_PROFIT_PROFILES = ("mean_reversion_v1", "mean_reversion_v2")


@dataclass(frozen=True)
class TargetProfitSensitivityResult:
    target_profit: float
    open_cycles_count: int
    would_close_now_count: int
    would_close_now_rate: float
    avg_distance_to_target: float | None
    gross_profit_min: float | None
    gross_profit_max: float | None
    net_profit_min: float | None
    net_profit_max: float | None
    profitable_now_count: int


@dataclass(frozen=True)
class TargetProfitRecommendation:
    target_profit: float
    reason: str


@dataclass(frozen=True)
class TargetProfitSensitivityReport:
    profile: str
    current_price: float
    configured_target_profit: float
    fee_rates: FeeRates
    results: list[TargetProfitSensitivityResult]
    recommendation: TargetProfitRecommendation | None


class TargetProfitSensitivityEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)
        self.fee_rates = FeeRateProvider(config).get_rates()

    def build_report(
        self,
        *,
        current_price: float,
        profile: str = "mean_reversion_v2",
        target_values: tuple[float, ...] = DEFAULT_TARGET_PROFIT_VALUES,
    ) -> TargetProfitSensitivityReport:
        if profile not in SUPPORTED_TARGET_PROFIT_PROFILES:
            supported = ", ".join(SUPPORTED_TARGET_PROFIT_PROFILES)
            raise ValueError(f"Unsupported target-profit sensitivity profile: {profile}. Supported: {supported}")

        cycles = self._load_open_cycles(profile)
        results = [
            self._evaluate_target(cycles, current_price, target_profit)
            for target_profit in target_values
        ]
        return TargetProfitSensitivityReport(
            profile=profile,
            current_price=current_price,
            configured_target_profit=self.config.target_profit,
            fee_rates=self.fee_rates,
            results=results,
            recommendation=self._recommend(results),
        )

    def _evaluate_target(
        self,
        cycles: list[dict],
        current_price: float,
        target_profit: float,
    ) -> TargetProfitSensitivityResult:
        distances: list[float] = []
        gross_profits: list[float] = []
        net_profits: list[float] = []
        would_close_now_count = 0
        profitable_now_count = 0

        for cycle in cycles:
            target_price = self._target_price(cycle["direction"], cycle["open_price"], target_profit)
            if self._close_condition_met(cycle["direction"], current_price, target_price):
                would_close_now_count += 1

            distance = self._distance_to_target(cycle["direction"], current_price, target_price)
            distances.append(distance)

            target_profit_result = self.fee_engine.calculate_profit(
                direction=cycle["direction"],
                open_price=cycle["open_price"],
                close_price=target_price,
                quantity=cycle["quantity"],
                use_taker_fee=True,
            )
            gross_profits.append(target_profit_result.gross_profit)
            net_profits.append(target_profit_result.net_profit)

            current_profit_result = self.fee_engine.calculate_profit(
                direction=cycle["direction"],
                open_price=cycle["open_price"],
                close_price=current_price,
                quantity=cycle["quantity"],
                use_taker_fee=True,
            )
            if current_profit_result.net_profit > 0:
                profitable_now_count += 1

        return TargetProfitSensitivityResult(
            target_profit=target_profit,
            open_cycles_count=len(cycles),
            would_close_now_count=would_close_now_count,
            would_close_now_rate=would_close_now_count / len(cycles) if cycles else 0.0,
            avg_distance_to_target=sum(distances) / len(distances) if distances else None,
            gross_profit_min=min(gross_profits) if gross_profits else None,
            gross_profit_max=max(gross_profits) if gross_profits else None,
            net_profit_min=min(net_profits) if net_profits else None,
            net_profit_max=max(net_profits) if net_profits else None,
            profitable_now_count=profitable_now_count,
        )

    def _load_open_cycles(self, profile: str) -> list[dict]:
        rows = self.database.load_open_paper_cycles(limit=1000)
        cycles = []
        for row in rows:
            (
                db_id,
                _timestamp,
                cycle_id,
                strategy_profile,
                direction,
                _status,
                open_price,
                _close_price,
                quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                _net_profit,
                opened_at,
                _closed_at,
            ) = row
            strategy_profile = clean_display_text(strategy_profile or "UNKNOWN")
            if strategy_profile != profile:
                continue
            cycles.append(
                {
                    "db_id": int(db_id),
                    "cycle_id": int(cycle_id),
                    "profile": strategy_profile,
                    "direction": clean_display_text(direction),
                    "open_price": float(open_price),
                    "quantity": float(quantity),
                    "opened_at": clean_display_text(opened_at),
                }
            )
        return cycles

    @staticmethod
    def _target_price(direction: str, open_price: float, target_profit: float) -> float:
        if direction == "BUY_USDC":
            return open_price * (1 + target_profit)
        return open_price * (1 - target_profit)

    @staticmethod
    def _close_condition_met(direction: str, current_price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return current_price >= target_price
        if direction == "SELL_USDC":
            return current_price <= target_price
        return False

    @staticmethod
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _recommend(results: list[TargetProfitSensitivityResult]) -> TargetProfitRecommendation | None:
        viable = [
            result
            for result in results
            if result.open_cycles_count > 0
            and result.would_close_now_count > 0
            and result.net_profit_min is not None
            and result.net_profit_min > 0
        ]
        if not viable:
            return None

        selected = max(
            viable,
            key=lambda result: (
                result.would_close_now_rate,
                result.target_profit,
            ),
        )
        return TargetProfitRecommendation(
            target_profit=selected.target_profit,
            reason=(
                "Highest tested target with positive net profit among variants that "
                "would close at least one currently open cycle now."
            ),
        )
