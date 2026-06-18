from datetime import datetime

from config.config_manager import BotConfig
from market.models import MarketState
from strategy.decision_engine import DecisionEngine
from strategy.models import TradeDecision


SMALL_TARGET_MULTIPLIER = 0.25
SUPPORTED_RUNTIME_STRATEGY_PROFILES = (
    "strict_current",
    "mean_reversion_v1",
    "mean_reversion_v2",
    "mean_reversion_v2_small_target",
    "mean_reversion_v2_small_target_ny",
    "mean_reversion_v2_small_target_tol1",
)


class StrategyProfileDecisionEngine:
    def __init__(self, config: BotConfig, profile: str = "strict_current") -> None:
        if profile not in SUPPORTED_RUNTIME_STRATEGY_PROFILES:
            supported = ", ".join(SUPPORTED_RUNTIME_STRATEGY_PROFILES)
            raise ValueError(f"Unsupported strategy profile: {profile}. Supported: {supported}")

        self.config = config
        self.profile = profile
        self.strict_engine = DecisionEngine(config)

    def make_decision(self, market_state: MarketState) -> TradeDecision:
        if self.profile == "strict_current":
            return self.strict_engine.make_decision(market_state)
        if self.profile in {
            "mean_reversion_v2",
            "mean_reversion_v2_small_target",
            "mean_reversion_v2_small_target_ny",
            "mean_reversion_v2_small_target_tol1",
        }:
            return self._mean_reversion_decision(
                market_state,
                profile_name=self.profile,
                buy_zone_max=25.0,
                sell_zone_min=75.0,
            )
        return self._mean_reversion_decision(
            market_state,
            profile_name="mean_reversion_v1",
            buy_zone_max=self.config.buy_zone_max,
            sell_zone_min=self.config.sell_zone_min,
        )

    def _mean_reversion_decision(
        self,
        market_state: MarketState,
        profile_name: str,
        buy_zone_max: float,
        sell_zone_min: float,
    ) -> TradeDecision:
        if not (0.0 < market_state.spread <= self.config.max_allowed_spread):
            return self._decision("WAIT", f"{profile_name}: spread invalid", "LOW", 0.0)

        if (
            market_state.market_health_score < self.config.min_market_health_score
            or market_state.market_health_status == "UNHEALTHY"
        ):
            return self._decision("SAFE_WAIT", f"{profile_name}: market health invalid", "LOW", 0.0)

        if market_state.market_regime == "ABNORMAL":
            return self._decision("SAFE_WAIT", f"{profile_name}: abnormal market regime", "LOW", 0.0)

        if market_state.volatility_regime == "EXTREME":
            return self._decision("SAFE_WAIT", f"{profile_name}: extreme volatility", "LOW", 0.0)

        if profile_name == "mean_reversion_v2_small_target_ny" and not self._is_new_york_session(market_state.created_at):
            return self._decision("WAIT", f"{profile_name}: outside NEW_YORK session", "LOW", 0.0)

        if market_state.work_position <= buy_zone_max:
            if market_state.micro_trend != "BUY_DOMINANT":
                return self._decision("WAIT", f"{profile_name}: BUY micro trend not confirmed", "LOW", 0.0)
            return self._decision(
                "BUY_USDC",
                f"{profile_name}: lower entry zone with BUY_DOMINANT micro trend",
                "MEDIUM",
                self._entry_score(market_state),
            )

        if market_state.work_position >= sell_zone_min:
            if market_state.micro_trend != "SELL_DOMINANT":
                return self._decision("WAIT", f"{profile_name}: SELL micro trend not confirmed", "LOW", 0.0)
            return self._decision(
                "SELL_USDC",
                f"{profile_name}: upper entry zone with SELL_DOMINANT micro trend",
                "MEDIUM",
                self._entry_score(market_state),
            )

        return self._decision("WAIT", f"{profile_name}: price outside entry zones", "LOW", 0.0)

    def _entry_score(self, market_state: MarketState) -> float:
        zone_depth = 100.0
        if self.config.buy_zone_max < market_state.work_position < self.config.sell_zone_min:
            zone_depth = 0.0
        return max(self.config.min_cycle_prediction_score, zone_depth)

    @staticmethod
    def _is_new_york_session(created_at: datetime) -> bool:
        return 17 <= created_at.hour <= 23

    def _decision(self, action: str, reason: str, confidence: str, score: float) -> TradeDecision:
        target_profit = self.config.target_profit
        if self.profile in {
            "mean_reversion_v2_small_target",
            "mean_reversion_v2_small_target_ny",
            "mean_reversion_v2_small_target_tol1",
        }:
            target_profit *= SMALL_TARGET_MULTIPLIER

        return TradeDecision(
            action=action,
            reason=reason,
            confidence=confidence,
            cycle_prediction_score=score,
            recommended_trade_size=0.0,
            target_profit=target_profit,
            created_at=datetime.utcnow(),
        )
