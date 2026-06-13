from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from backtest.backtest_engine import BacktestEngine
from backtest.historical_data_provider import HistoricalCandle
from config.config_manager import BotConfig
from analytics.ml_dataset_exporter import SUPPORTED_DATASET_MODES
from market.models import MarketState
from strategy.profile_decision_engine import StrategyProfileDecisionEngine


@dataclass(frozen=True)
class MLDatasetCoverageReport:
    profile: str
    dataset_mode: str
    total_rows: int
    candidate_rows: int
    buy_zone_count: int
    sell_zone_count: int
    work_position_min: float | None
    work_position_max: float | None
    work_position_avg: float | None
    micro_trend_distribution: dict[str, int]
    entry_zone_pass_count: int
    micro_trend_pass_count: int
    safety_filters_pass_count: int
    all_filters_pass_count: int
    recommendation: str


class MLDatasetCoverageEngine:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def build_report(
        self,
        *,
        candles: list[HistoricalCandle],
        profile: str,
        dataset_mode: str = "profile",
    ) -> MLDatasetCoverageReport:
        self._validate_dataset_mode(dataset_mode)
        if len(candles) < 31:
            return MLDatasetCoverageReport(
                profile=profile,
                dataset_mode=dataset_mode,
                total_rows=0,
                candidate_rows=0,
                buy_zone_count=0,
                sell_zone_count=0,
                work_position_min=None,
                work_position_max=None,
                work_position_avg=None,
                micro_trend_distribution={},
                entry_zone_pass_count=0,
                micro_trend_pass_count=0,
                safety_filters_pass_count=0,
                all_filters_pass_count=0,
                recommendation="increase limit: not enough candles to build feature rows.",
            )

        state_builder = BacktestEngine(self.config)
        decision_engine = StrategyProfileDecisionEngine(self.config, profile)
        closes = [candle.close for candle in candles]
        work_positions: list[float] = []
        micro_trends: Counter[str] = Counter()
        candidate_rows = 0
        buy_zone_count = 0
        sell_zone_count = 0
        entry_zone_pass_count = 0
        micro_trend_pass_count = 0
        safety_filters_pass_count = 0
        all_filters_pass_count = 0

        for index in range(30, len(candles)):
            candle = candles[index]
            window = closes[max(0, index - 30):index]
            state = state_builder._build_state(current_price=candle.close, prices=window)
            decision = decision_engine.make_decision(state)
            candidate_direction = self._candidate_direction(
                state=state,
                profile=profile,
                dataset_mode=dataset_mode,
                profile_action=decision.action,
            )
            if candidate_direction in {"BUY_USDC", "SELL_USDC"}:
                candidate_rows += 1

            work_positions.append(state.work_position)
            micro_trends[state.micro_trend] += 1

            is_buy_zone = state.work_position <= self._buy_zone_max(profile)
            is_sell_zone = state.work_position >= self._sell_zone_min(profile)
            if is_buy_zone:
                buy_zone_count += 1
            if is_sell_zone:
                sell_zone_count += 1
            in_entry_zone = is_buy_zone or is_sell_zone
            if in_entry_zone:
                entry_zone_pass_count += 1
            if self._micro_trend_passes(state, is_buy_zone, is_sell_zone):
                micro_trend_pass_count += 1
            if self._safety_filters_pass(state):
                safety_filters_pass_count += 1
            if candidate_direction in {"BUY_USDC", "SELL_USDC"}:
                all_filters_pass_count += 1

        return MLDatasetCoverageReport(
            profile=profile,
            dataset_mode=dataset_mode,
            total_rows=len(work_positions),
            candidate_rows=candidate_rows,
            buy_zone_count=buy_zone_count,
            sell_zone_count=sell_zone_count,
            work_position_min=min(work_positions) if work_positions else None,
            work_position_max=max(work_positions) if work_positions else None,
            work_position_avg=sum(work_positions) / len(work_positions) if work_positions else None,
            micro_trend_distribution=dict(sorted(micro_trends.items())),
            entry_zone_pass_count=entry_zone_pass_count,
            micro_trend_pass_count=micro_trend_pass_count,
            safety_filters_pass_count=safety_filters_pass_count,
            all_filters_pass_count=all_filters_pass_count,
            recommendation=self._recommendation(
                dataset_mode=dataset_mode,
                total_rows=len(work_positions),
                entry_zone_pass_count=entry_zone_pass_count,
                micro_trend_pass_count=micro_trend_pass_count,
                safety_filters_pass_count=safety_filters_pass_count,
                all_filters_pass_count=all_filters_pass_count,
            ),
        )

    def _buy_zone_max(self, profile: str) -> float:
        if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"}:
            return 25.0
        return self.config.buy_zone_max

    def _sell_zone_min(self, profile: str) -> float:
        if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"}:
            return 75.0
        return self.config.sell_zone_min

    def _micro_trend_passes(self, state: MarketState, is_buy_zone: bool, is_sell_zone: bool) -> bool:
        return (
            (is_buy_zone and state.micro_trend == "BUY_DOMINANT")
            or (is_sell_zone and state.micro_trend == "SELL_DOMINANT")
        )

    def _candidate_direction(
        self,
        *,
        state: MarketState,
        profile: str,
        dataset_mode: str,
        profile_action: str,
    ) -> str:
        if dataset_mode == "profile":
            return profile_action if profile_action in {"BUY_USDC", "SELL_USDC"} else "WAIT"

        if not self._safety_filters_pass(state):
            return "WAIT"
        if state.work_position <= self._buy_zone_max(profile):
            return "BUY_USDC"
        if state.work_position >= self._sell_zone_min(profile):
            return "SELL_USDC"
        return "WAIT"

    def _safety_filters_pass(self, state: MarketState) -> bool:
        return (
            0.0 < state.spread <= self.config.max_allowed_spread
            and state.market_health_score >= self.config.min_market_health_score
            and state.market_health_status != "UNHEALTHY"
            and state.market_regime != "ABNORMAL"
            and state.volatility_regime != "EXTREME"
        )

    @staticmethod
    def _recommendation(
        *,
        dataset_mode: str,
        total_rows: int,
        entry_zone_pass_count: int,
        micro_trend_pass_count: int,
        safety_filters_pass_count: int,
        all_filters_pass_count: int,
    ) -> str:
        if total_rows < 500:
            return "increase limit: dataset window is small."
        if entry_zone_pass_count == 0:
            return "change interval or relax thresholds: no historical rows entered BUY/SELL zones."
        if safety_filters_pass_count == 0:
            return "dataset not suitable: safety filters reject all rows."
        if dataset_mode == "profile" and micro_trend_pass_count == 0:
            return "dataset not suitable: historical klines do not provide confirming micro_trend for this profile."
        if all_filters_pass_count == 0:
            return "relax thresholds: entry zones exist but no row passes all profile filters."
        if all_filters_pass_count < 20:
            return "increase limit: very few candidate rows for supervised learning."
        if dataset_mode == "no_micro_trend" and micro_trend_pass_count == 0:
            return "dataset suitable for exploratory labels; micro_trend is intentionally ignored."
        return "dataset suitable for exploratory ML labeling."

    @staticmethod
    def _validate_dataset_mode(dataset_mode: str) -> None:
        if dataset_mode not in SUPPORTED_DATASET_MODES:
            supported = ", ".join(SUPPORTED_DATASET_MODES)
            raise ValueError(f"Unsupported dataset mode: {dataset_mode}. Supported: {supported}")
